pub mod config;
pub mod keep_awake;
pub mod project;
pub mod pty_manager;
pub mod sidecar;
pub mod sidecar_verify;

use futures_util::StreamExt;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex as StdMutex};
use std::{path::PathBuf, time::Duration, time::Instant};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, Wry};
use tokio::io::AsyncWriteExt;

// ---------------------------------------------------------------------------
// ProgressCache: in-memory snapshot of latest EvolvePro run progress per run_id.
// Lets the frontend recover UI state after a webview reload (Ctrl+R / HMR).
// Cache is cleared on app restart by design (no persistence).
// ---------------------------------------------------------------------------

#[derive(Clone, serde::Serialize, serde::Deserialize, Debug)]
pub struct EvolveProProgressSnapshot {
    pub run_id: String,
    pub stage: String,
    pub current: u64,
    pub total: u64,
    pub message: String,
    pub updated_at_ms: u64,
}

#[derive(Default)]
pub struct ProgressCache(pub StdMutex<HashMap<String, EvolveProProgressSnapshot>>);

fn now_ms() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// Update the ProgressCache from an evolvepro progress notification.
///
/// `params` is the already-unwrapped `params` object of a `progress` JSON-RPC
/// notification (the sidecar manager's `on_progress` callback passes it
/// pre-extracted). Only entries tagged `type == "evolvepro_progress"` are cached.
pub fn cache_evolvepro_progress(app: &AppHandle<Wry>, params: &Value) {
    if params.get("type").and_then(|v| v.as_str()) != Some("evolvepro_progress") {
        return;
    }
    let run_id = match params.get("run_id").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return,
    };
    let snap = EvolveProProgressSnapshot {
        run_id: run_id.clone(),
        stage: params
            .get("stage")
            .and_then(|v| v.as_str())
            .unwrap_or("loading")
            .to_string(),
        current: params.get("current").and_then(|v| v.as_u64()).unwrap_or(0),
        total: params.get("total").and_then(|v| v.as_u64()).unwrap_or(0),
        message: params
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        updated_at_ms: now_ms(),
    };
    if let Some(cache) = app.try_state::<ProgressCache>() {
        if let Ok(mut m) = cache.0.lock() {
            m.insert(run_id, snap);
        }
    }
}

#[tauri::command]
fn get_run_progress(
    state: State<ProgressCache>,
    run_id: String,
) -> Option<EvolveProProgressSnapshot> {
    state.0.lock().ok()?.get(&run_id).cloned()
}

#[tauri::command]
fn list_active_runs(state: State<ProgressCache>) -> Vec<EvolveProProgressSnapshot> {
    state
        .0
        .lock()
        .map(|m| m.values().cloned().collect())
        .unwrap_or_default()
}

// ---------------------------------------------------------------------------
// DownloadState + ESM2 model download commands
// ---------------------------------------------------------------------------

type CancelsMap = Arc<StdMutex<HashMap<String, Arc<AtomicBool>>>>;

struct DownloadState {
    cancels: CancelsMap,
}

impl Default for DownloadState {
    fn default() -> Self {
        Self {
            cancels: Arc::new(StdMutex::new(HashMap::new())),
        }
    }
}

const ALLOWED_URL_PREFIX: &str = "https://dl.fbaipublicfiles.com/fair-esm/models/";

const ALLOWED_MODEL_IDS: &[&str] = &[
    "esm2_t6_8M_UR50D",
    "esm2_t12_35M_UR50D",
    "esm2_t30_150M_UR50D",
    "esm2_t33_650M_UR50D",
    "esm2_t36_3B_UR50D",
    "esm2_t48_15B_UR50D",
];

fn esm2_cache_path() -> Result<PathBuf, String> {
    esm2_candidate_cache_dirs()
        .into_iter()
        .next()
        .ok_or_else(|| "no candidate cache dirs (HOME/USERPROFILE missing)".to_string())
}

/// Return ordered candidate cache directories where ESM2 .pt files may live.
/// First entry is also the canonical write target.
fn esm2_candidate_cache_dirs() -> Vec<PathBuf> {
    let var = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    let home = std::env::var(var).ok();
    let mut out: Vec<PathBuf> = Vec::new();

    // 1. TORCH_HOME/hub/checkpoints (torch's documented override)
    if let Ok(th) = std::env::var("TORCH_HOME") {
        out.push(PathBuf::from(th).join("hub").join("checkpoints"));
    }
    // 2. XDG_CACHE_HOME/torch/hub/checkpoints (Linux/macOS convention)
    if let Ok(xdg) = std::env::var("XDG_CACHE_HOME") {
        out.push(PathBuf::from(xdg).join("torch").join("hub").join("checkpoints"));
    }
    // 3. ~/.cache/torch/hub/checkpoints (torch default, all platforms)
    if let Some(ref h) = home {
        out.push(
            PathBuf::from(h)
                .join(".cache")
                .join("torch")
                .join("hub")
                .join("checkpoints"),
        );
    }
    // 4. Windows-specific AppData fallback
    if cfg!(windows) {
        if let Ok(la) = std::env::var("LOCALAPPDATA") {
            out.push(PathBuf::from(la).join("torch").join("hub").join("checkpoints"));
        }
    }
    out
}

/// Minimum size accepted as "installed". 1 MiB filters out empty/aborted writes
/// but tolerates byte-level mismatches against expected_bytes (relaxed integrity).
const ESM2_MIN_VALID_BYTES: u64 = 1 << 20;

fn validate_model_id(model_id: &str) -> Result<(), String> {
    if ALLOWED_MODEL_IDS.contains(&model_id) {
        Ok(())
    } else {
        Err(format!("model_id not in allowlist: {model_id}"))
    }
}

fn validate_url(url: &str) -> Result<(), String> {
    if url.starts_with(ALLOWED_URL_PREFIX) {
        Ok(())
    } else {
        Err(format!("URL must start with {ALLOWED_URL_PREFIX}"))
    }
}

#[tauri::command]
fn esm2_cache_dir() -> Result<String, String> {
    esm2_cache_path().map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
fn esm2_check_installed(model_id: String, expected_min_bytes: u64) -> Result<bool, String> {
    validate_model_id(&model_id)?;
    // Relax: accept any candidate cache dir whose file size is at least
    // min(expected_min_bytes, ESM2_MIN_VALID_BYTES). Strict byte equality
    // against expected_min_bytes was causing false negatives for files
    // downloaded via other tools (huggingface CDN, torch.hub auto-fetch).
    let threshold = std::cmp::min(expected_min_bytes, ESM2_MIN_VALID_BYTES).max(1);
    for dir in esm2_candidate_cache_dirs() {
        let path = dir.join(format!("{model_id}.pt"));
        if let Ok(meta) = std::fs::metadata(&path) {
            if meta.len() >= threshold {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

/// Diagnostic: list every cache dir checked + file presence/size for a model.
#[tauri::command]
fn esm2_diagnose(model_id: String) -> Result<Vec<serde_json::Value>, String> {
    validate_model_id(&model_id)?;
    let report = esm2_candidate_cache_dirs()
        .into_iter()
        .map(|dir| {
            let path = dir.join(format!("{model_id}.pt"));
            let (exists, size) = match std::fs::metadata(&path) {
                Ok(m) => (true, m.len()),
                Err(_) => (false, 0u64),
            };
            serde_json::json!({
                "path": path.to_string_lossy(),
                "exists": exists,
                "size": size,
            })
        })
        .collect();
    Ok(report)
}

#[tauri::command]
async fn esm2_download_start(
    model_id: String,
    url: String,
    expected_bytes: Option<u64>,
    state: State<'_, DownloadState>,
    app: AppHandle<Wry>,
) -> Result<(), String> {
    validate_model_id(&model_id)?;
    validate_url(&url)?;

    let cancel_flag = Arc::new(AtomicBool::new(false));

    {
        let mut map = state
            .cancels
            .lock()
            .map_err(|_| "lock poisoned".to_string())?;
        if map.contains_key(&model_id) {
            return Err(format!("download already in progress for {model_id}"));
        }
        map.insert(model_id.clone(), cancel_flag.clone());
    }

    let cancels: CancelsMap = state.cancels.clone();

    tokio::spawn(async move {
        let result =
            run_esm2_download(&model_id, &url, expected_bytes, &cancel_flag, &app).await;

        let payload = match &result {
            Ok(true) => serde_json::json!({
                "model_id": model_id,
                "bytes": expected_bytes.unwrap_or(0),
                "total": expected_bytes.unwrap_or(0),
                "status": "done",
                "error": null,
            }),
            Ok(false) => serde_json::json!({
                "model_id": model_id,
                "bytes": 0,
                "total": expected_bytes.unwrap_or(0),
                "status": "cancelled",
                "error": null,
            }),
            Err(e) => serde_json::json!({
                "model_id": model_id,
                "bytes": 0,
                "total": expected_bytes.unwrap_or(0),
                "status": "error",
                "error": e,
            }),
        };
        let _ = app.emit("esm2://download-progress", &payload);

        if let Ok(mut map) = cancels.lock() {
            map.remove(&model_id);
        }
    });

    Ok(())
}

async fn run_esm2_download(
    model_id: &str,
    url: &str,
    expected_bytes: Option<u64>,
    cancel: &AtomicBool,
    app: &AppHandle<Wry>,
) -> Result<bool, String> {
    let cache_dir = esm2_cache_path()?;
    std::fs::create_dir_all(&cache_dir)
        .map_err(|e| format!("failed to create cache dir: {e}"))?;

    let final_path = cache_dir.join(format!("{model_id}.pt"));
    let part_path = cache_dir.join(format!("{model_id}.pt.part"));

    let client = reqwest::Client::new();
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("HTTP request failed: {e}"))?;

    if !response.status().is_success() {
        return Err(format!("HTTP {}", response.status()));
    }

    let total = response.content_length().or(expected_bytes).unwrap_or(0);

    let mut file = tokio::fs::File::create(&part_path)
        .await
        .map_err(|e| format!("failed to create .part file: {e}"))?;

    let mut stream = response.bytes_stream();
    let mut downloaded: u64 = 0;
    let mut acc_bytes: u64 = 0;
    let mut last_emit = Instant::now();
    const EMIT_BYTES: u64 = 256 * 1024;
    const EMIT_INTERVAL: Duration = Duration::from_millis(100);

    while let Some(chunk) = stream.next().await {
        if cancel.load(Ordering::Relaxed) {
            drop(file);
            let _ = std::fs::remove_file(&part_path);
            return Ok(false);
        }

        let chunk = chunk.map_err(|e| format!("stream error: {e}"))?;
        file.write_all(&chunk)
            .await
            .map_err(|e| format!("write error: {e}"))?;

        downloaded += chunk.len() as u64;
        acc_bytes += chunk.len() as u64;

        if acc_bytes >= EMIT_BYTES || last_emit.elapsed() >= EMIT_INTERVAL {
            let payload = serde_json::json!({
                "model_id": model_id,
                "bytes": downloaded,
                "total": total,
                "status": "downloading",
                "error": null,
            });
            let _ = app.emit("esm2://download-progress", &payload);
            acc_bytes = 0;
            last_emit = Instant::now();
        }
    }

    file.flush()
        .await
        .map_err(|e| format!("flush error: {e}"))?;
    drop(file);

    std::fs::rename(&part_path, &final_path)
        .map_err(|e| {
            let _ = std::fs::remove_file(&part_path);
            format!("rename failed: {e}")
        })?;

    Ok(true)
}

#[tauri::command]
fn esm2_download_cancel(
    model_id: String,
    state: State<'_, DownloadState>,
) -> Result<(), String> {
    validate_model_id(&model_id)?;
    let map = state
        .cancels
        .lock()
        .map_err(|_| "lock poisoned".to_string())?;
    if let Some(flag) = map.get(&model_id) {
        flag.store(true, Ordering::Relaxed);
    }
    Ok(())
}

#[tauri::command]
async fn sidecar_rpc(
    kind: String,
    method: String,
    params: Value,
    timeout_ms: Option<u64>,
    state: State<'_, sidecar::SidecarManager>,
) -> Result<Value, String> {
    let timeout_override = timeout_ms.filter(|&v| v > 0).map(Duration::from_millis);
    state.rpc_with_timeout(&kind, &method, params, timeout_override).await
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
    if !matches!(kind.as_str(), "kuro" | "mame" | "evolvepro") {
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
        "evolvepro" => "evolvepro-sidecar",
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

// ---------------------------------------------------------------------------
// Miniforge prefix helpers (ported from evolvepro-gui; std-only, self-contained)
// ---------------------------------------------------------------------------

fn miniforge_install_prefix() -> Result<PathBuf, String> {
    if cfg!(windows) {
        let profile = std::env::var("USERPROFILE")
            .map_err(|_| "USERPROFILE not set".to_string())?;
        Ok(PathBuf::from(profile).join("miniforge3"))
    } else {
        let home = std::env::var("HOME")
            .map_err(|_| "HOME not set".to_string())?;
        Ok(PathBuf::from(home).join("miniforge3"))
    }
}

fn miniforge_conda_exe(prefix: &PathBuf) -> PathBuf {
    if cfg!(windows) {
        prefix.join("Scripts").join("conda.exe")
    } else {
        prefix.join("bin").join("conda")
    }
}

/// Check whether the conda executable at `conda_exe` responds correctly.
/// Uses a 3-second timeout to avoid hanging on a partially installed binary.
/// Returns true if conda is functional, false if the exe is absent, exits
/// non-zero, or the timeout fires.
fn verify_conda_exe(conda_exe: &PathBuf) -> bool {
    if !conda_exe.exists() {
        return false;
    }
    // Spawn with a dedicated thread so we can impose a wall-clock limit.
    let exe = conda_exe.clone();
    let (tx, rx) = std::sync::mpsc::channel::<bool>();
    std::thread::spawn(move || {
        let result = std::process::Command::new(&exe)
            .arg("--version")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output();
        match result {
            Ok(out) => {
                let stdout = String::from_utf8_lossy(&out.stdout);
                let ok = out.status.success() && stdout.contains("conda");
                let _ = tx.send(ok);
            }
            Err(_) => {
                let _ = tx.send(false);
            }
        }
    });
    rx.recv_timeout(std::time::Duration::from_secs(3))
        .unwrap_or(false)
}

/// Confirm the candidate path is exactly `{home}/miniforge3` to prevent
/// path-traversal attacks before any destructive operation.
fn validate_miniforge_prefix_path(candidate: &PathBuf) -> Result<(), String> {
    let expected = miniforge_install_prefix()?;
    // Compare as canonical-ish strings; do not follow symlinks via canonicalize
    // because the directory may not exist yet.  Compare component-by-component.
    if candidate != &expected {
        return Err(format!(
            "prefix path mismatch: expected {:?}, got {:?}",
            expected, candidate
        ));
    }
    Ok(())
}

/// Remove the Miniforge prefix directory after validating the path is exactly
/// `{home}/miniforge3`. The path is computed Rust-side; no user input is
/// accepted to prevent path-traversal.
#[tauri::command]
fn conda_install_remove_prefix() -> Result<(), String> {
    let prefix = miniforge_install_prefix()?;

    // Safety: confirm the path is exactly what we computed.
    validate_miniforge_prefix_path(&prefix)?;

    // Refuse if the directory is a symlink (extra safety).
    let meta = std::fs::symlink_metadata(&prefix)
        .map_err(|e| format!("cannot stat prefix: {e}"))?;
    if meta.file_type().is_symlink() {
        return Err("prefix is a symlink; remove it manually".to_string());
    }

    // Final check: conda must still be non-functional (user could have fixed it
    // between the conflict detection and clicking [Remove]).
    let conda_exe = miniforge_conda_exe(&prefix);
    if verify_conda_exe(&conda_exe) {
        return Err(
            "conda appears functional now; removal cancelled to prevent data loss".to_string(),
        );
    }

    std::fs::remove_dir_all(&prefix)
        .map_err(|e| format!("failed to remove prefix: {e}"))?;

    Ok(())
}

// ---------------------------------------------------------------------------
// File preview / probe commands (used by the EVOLVEpro run form for input
// validation). `read_text_head` reads at most `max_bytes` so very large files
// do not block the UI; `probe_writable_dir` performs a write/remove cycle.
// ---------------------------------------------------------------------------

#[tauri::command]
fn read_text_head(path: String, max_bytes: usize) -> Result<String, String> {
    use std::io::Read;
    let cap = max_bytes.min(1024 * 1024);
    let mut f = std::fs::File::open(&path).map_err(|e| format!("open failed: {e}"))?;
    let mut buf = vec![0u8; cap];
    let n = f.read(&mut buf).map_err(|e| format!("read failed: {e}"))?;
    buf.truncate(n);
    Ok(String::from_utf8_lossy(&buf).into_owned())
}

#[tauri::command]
fn probe_writable_dir(path: String) -> Result<(), String> {
    let dir = std::path::Path::new(&path);
    if !dir.is_dir() {
        return Err("not a directory".to_string());
    }
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let probe = dir.join(format!(".kuma_write_probe_{ts}"));
    std::fs::write(&probe, b"probe").map_err(|e| format!("write failed: {e}"))?;
    let _ = std::fs::remove_file(&probe);
    Ok(())
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
        manager.graceful_kill("mame", 2),
        manager.graceful_kill("evolvepro", 2)
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
            app.manage(pty_manager::PtyState::default());
            app.manage(ProgressCache::default());
            app.manage(DownloadState::default());
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
            pty_manager::pty_spawn,
            pty_manager::pty_write,
            pty_manager::pty_resize,
            pty_manager::pty_kill,
            esm2_cache_dir,
            esm2_check_installed,
            esm2_diagnose,
            esm2_download_start,
            esm2_download_cancel,
            get_run_progress,
            list_active_runs,
            conda_install_remove_prefix,
            read_text_head,
            probe_writable_dir,
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
