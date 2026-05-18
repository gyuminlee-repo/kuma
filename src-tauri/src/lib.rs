pub mod config;
pub mod keep_awake;
pub mod project;
pub mod sidecar;
pub mod sidecar_verify;

use serde_json::Value;
use std::{path::PathBuf, time::Duration};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, Wry};

#[tauri::command]
async fn sidecar_rpc(
    kind: String,
    method: String,
    params: Value,
    state: State<'_, sidecar::SidecarManager>,
) -> Result<Value, String> {
    state.rpc(&kind, &method, params).await
}

#[tauri::command]
async fn sidecar_kill(
    kind: String,
    state: State<'_, sidecar::SidecarManager>,
) -> Result<(), String> {
    state.kill(&kind).await
}

#[tauri::command]
async fn sidecar_is_running(
    kind: String,
    state: State<'_, sidecar::SidecarManager>,
) -> Result<bool, String> {
    state.is_running(&kind).await
}

/// 사이드카 프로세스의 상태를 확인한다.
///
/// `invoke('check_sidecar_health', { kind: 'kuro' | 'mame' })` 형태로 호출.
/// - `alive: false` — 사이드카가 실행 중이 아님. 스폰하지 않음.
/// - `alive: true`  — 실행 중. `health_info` RPC 결과(pid, py_version)와
///                    Rust 측 uptime_secs를 함께 반환.
///
/// 중요: 이 커맨드는 사이드카를 새로 스폰하지 않는다.
/// 스폰이 필요하면 `sidecar_rpc`를 호출해야 한다.
#[derive(serde::Serialize)]
struct SidecarHealth {
    alive: bool,
    responsive: bool,   // health_info RPC 응답을 받았는가
    kind: String,
    pid: Option<u32>,
    version: Option<String>,   // sidecar Python 인터프리터 버전 (py_version)
    uptime_secs: Option<u64>,
    message: String,
}

#[tauri::command]
async fn check_sidecar_health(
    kind: String,
    state: State<'_, sidecar::SidecarManager>,
) -> Result<SidecarHealth, String> {
    // 0. kind allow-list 가드
    if !matches!(kind.as_str(), "kuro" | "mame") {
        return Err(format!("invalid sidecar kind: {kind}"));
    }

    // 1. Spawn 없이 alive 여부만 확인
    let is_alive = state.is_running(&kind).await?;
    if !is_alive {
        return Ok(SidecarHealth {
            alive: false,
            responsive: false,
            kind: kind.clone(),
            pid: None,
            version: None,
            uptime_secs: None,
            message: format!("{kind} 사이드카가 실행 중이 아닙니다."),
        });
    }

    // 2. Rust 측에서 uptime 스냅샷 (RPC 없이)
    let snapshot = state.health_snapshot(&kind).await?;
    let uptime_secs = snapshot.map(|(_, uptime)| uptime);

    // 3. 이미 실행 중인 프로세스에 health_info RPC 전송 (spawn 없음, 2초 타임아웃)
    let rpc_result = match tokio::time::timeout(
        Duration::from_secs(2),
        state.rpc(&kind, "health_info", serde_json::json!({})),
    )
    .await
    {
        Ok(inner) => inner,
        Err(_) => Err(format!("{kind} health_info 응답 타임아웃(2초)")),
    };

    match rpc_result {
        Ok(info) => {
            let pid = info.get("pid").and_then(|v| v.as_u64()).and_then(|v| u32::try_from(v).ok());
            let py_version = info
                .get("py_version")
                .and_then(|v| v.as_str())
                .map(str::to_owned);
            let message = match (pid, py_version.as_deref(), uptime_secs) {
                (Some(p), Some(ver), Some(up)) => {
                    format!("{kind} 사이드카 정상 (PID {p}, Python {ver}, 가동 {up}초)")
                }
                (Some(p), Some(ver), None) => {
                    format!("{kind} 사이드카 정상 (PID {p}, Python {ver})")
                }
                _ => format!("{kind} 사이드카 응답 수신"),
            };
            Ok(SidecarHealth {
                alive: true,
                responsive: true,
                kind,
                pid,
                version: py_version,
                uptime_secs,
                message,
            })
        }
        Err(err) => {
            // health_info RPC 실패(응답 없음 또는 타임아웃) = 프로세스는 살아있으나 응답 불가
            Ok(SidecarHealth {
                alive: true,
                responsive: false,
                kind: kind.clone(),
                pid: None,
                version: None,
                uptime_secs,
                message: format!("{kind} 사이드카 응답 없음: {err}"),
            })
        }
    }
}

/// §6 Settings: Return the resolved on-disk path for a sidecar binary.
///
/// Uses the same path resolution as `verify_binary_hash` in sidecar.rs:
///   `current_exe().parent() / "{kind}-sidecar[.exe]"`
///
/// On all platforms Tauri strips the target-triple suffix from externalBin
/// names in release bundles, so the binary is always at the bare base name.
/// Returns an error string on failure so the frontend can display a fallback.
#[tauri::command]
fn get_sidecar_path(kind: String) -> Result<String, String> {
    let base_name = match kind.as_str() {
        "kuro" => "kuro-sidecar",
        "mame" => "mame-sidecar",
        other => return Err(format!("Unknown sidecar kind: {other}")),
    };
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("Cannot resolve executable: {e}"))?
        .parent()
        .ok_or_else(|| "Executable has no parent directory".to_string())?
        .to_path_buf();
    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let path = exe_dir.join(format!("{base_name}{ext}"));
    Ok(path.display().to_string())
}

/// §11 Build & Distribution: macOS ad-hoc codesign status indicator.
/// On macOS, runs `codesign -dv --verbose=2 <bundle>` and parses the output
/// to determine signing state. On non-macOS returns "N/A (non-macOS)".
#[tauri::command]
fn get_codesign_status(app: AppHandle) -> String {
    #[cfg(target_os = "macos")]
    {
        // Resolve the .app bundle path from the executable path
        // e.g. /Applications/Kuma.app/Contents/MacOS/kuma → /Applications/Kuma.app
        let exe_path = match app.path().resource_dir() {
            Ok(p) => p,
            Err(_) => return "unknown (path error)".to_string(),
        };
        // Walk up to find the .app bundle root (ends with .app)
        let bundle_path: PathBuf = {
            let mut p = exe_path.clone();
            loop {
                if p.extension().and_then(|e| e.to_str()) == Some("app") {
                    break p;
                }
                if !p.pop() {
                    // No .app ancestor found; fall back to resource dir
                    break exe_path.clone();
                }
            }
        };

        match std::process::Command::new("codesign")
            .args(["-dv", "--verbose=2", bundle_path.to_str().unwrap_or(".")])
            .output()
        {
            Ok(output) => {
                // codesign writes info to stderr
                let stderr = String::from_utf8_lossy(&output.stderr);
                let stdout = String::from_utf8_lossy(&output.stdout);
                let combined = format!("{stderr}{stdout}");

                if !output.status.success() && combined.is_empty() {
                    return "unsigned".to_string();
                }
                // Ad-hoc: Authority line absent or "adhoc" flag present
                if combined.contains("flags=0x20002(adhoc)")
                    || combined.contains("Signature=adhoc")
                    || (!combined.contains("Authority=") && output.status.success())
                {
                    "ad-hoc".to_string()
                } else if combined.contains("Authority=Developer ID") {
                    "signed (Developer ID)".to_string()
                } else if combined.contains("Authority=Apple") {
                    "signed (Apple)".to_string()
                } else if combined.contains("Authority=") {
                    "signed".to_string()
                } else {
                    "unsigned".to_string()
                }
            }
            Err(_) => "unknown (codesign not found)".to_string(),
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        // Suppress unused variable warning on non-macOS
        let _ = app;
        "N/A (non-macOS)".to_string()
    }
}

async fn shutdown_sidecars_async(app: &AppHandle<Wry>) {
    let manager = app.state::<sidecar::SidecarManager>();
    // §22: Send shutdown RPC, wait briefly, then force-kill as fallback.
    // sidecar_kill (Tauri command) still calls kill() directly for
    // immediate force-kill paths (user cancel, cancelAndRespawn).
    // RunEvent::Exit must not keep the desktop app visibly alive for a long
    // sequential shutdown path, so both sidecars are swept concurrently.
    let _ = tokio::join!(
        manager.graceful_kill("kuro", 2),
        manager.graceful_kill("mame", 2)
    );
}

pub fn run() {
    let app = match tauri::Builder::default()
        // single-instance: 두 번째 실행 시 첫 창에 포커스 + 프론트엔드 알림 (desktop only)
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            eprintln!("[lifecycle] second instance attempted → focusing main window");
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
                // JS MainShell이 구독해 statusMessage로 표시
                let _ = app.emit_to("main", "second-instance-attempted", ());
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            let binaries_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| PathBuf::from("src-tauri/binaries"));
            app.manage(sidecar::SidecarManager::new(app.handle().clone(), binaries_dir));
            Ok(())
        })
        // CloseRequested is handled entirely in MainShell.tsx (JS side):
        //   confirm busy state → flushAutosave → getCurrentWindow().destroy()
        // RunEvent::Exit below handles the final sidecar cleanup sweep.
        .invoke_handler(tauri::generate_handler![
            config::get_config_cmd,
            config::set_projects_root_cmd,
            config::create_project_cmd,
            config::load_project_cmd,
            config::list_recent_projects_cmd,
            config::remove_recent_project_cmd,
            sidecar_rpc,
            sidecar_kill,
            sidecar_is_running,
            check_sidecar_health,
            keep_awake::keep_awake_start,
            keep_awake::keep_awake_stop,
            get_codesign_status,
            get_sidecar_path,
        ])
        .build(tauri::generate_context!())
    {
        Ok(app) => app,
        Err(e) => {
            eprintln!("Fatal: {e}");
            std::process::exit(1);
        }
    };

    app.run(|app_handle, event| {
        // Final-stage cleanup: if Exit fires without going through our
        // CloseRequested path (e.g., OS quit signal, app.exit() from elsewhere),
        // make a best-effort sync sweep so sidecar children don't outlive us.
        if matches!(event, RunEvent::Exit) {
            eprintln!("[lifecycle] RunEvent::Exit → final sidecar sweep");
            tauri::async_runtime::block_on(shutdown_sidecars_async(app_handle));
        }
    });
}
