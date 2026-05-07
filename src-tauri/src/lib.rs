pub mod config;
pub mod keep_awake;
pub mod project;
pub mod sidecar;
pub mod sidecar_verify;

use serde_json::Value;
use std::path::PathBuf;
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

async fn shutdown_sidecars_async(app: &AppHandle<Wry>) {
    let manager = app.state::<sidecar::SidecarManager>();
    // §22: Send shutdown RPC, wait up to 5 s, then force-kill as fallback.
    // sidecar_kill (Tauri command) still calls kill() directly for
    // immediate force-kill paths (user cancel, cancelAndRespawn).
    let _ = manager.graceful_kill("kuro", 5).await;
    let _ = manager.graceful_kill("mame", 5).await;
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
            sidecar_rpc,
            sidecar_kill,
            sidecar_is_running,
            keep_awake::keep_awake_start,
            keep_awake::keep_awake_stop,
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
