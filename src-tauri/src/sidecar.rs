use serde::Serialize;
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicI64, Ordering},
        Arc,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, Wry};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use tokio::sync::{oneshot, Mutex, Notify};

// `wait_ready` is retained for diagnostic / future use, but `ensure_spawned`
// no longer blocks on the ready notification. The 30s budget is what would
// have applied; left here so callers that opt into ready-gating still have a
// reasonable upper bound.
#[allow(dead_code)]
const READY_TIMEOUT: Duration = Duration::from_secs(30);
const RPC_TIMEOUT: Duration = Duration::from_secs(60);

type PendingSender = oneshot::Sender<Result<Value, String>>;

#[derive(Serialize, Clone)]
struct SidecarProgressPayload {
    kind: String,
    params: Value,
}

pub struct LineProtocol {
    pending: Arc<Mutex<HashMap<i64, PendingSender>>>,
    stdout_buffer: Arc<Mutex<String>>,
    ready: Arc<AtomicBool>,
    ready_notify: Arc<Notify>,
}

impl LineProtocol {
    pub fn new() -> Self {
        Self {
            pending: Arc::new(Mutex::new(HashMap::new())),
            stdout_buffer: Arc::new(Mutex::new(String::new())),
            ready: Arc::new(AtomicBool::new(false)),
            ready_notify: Arc::new(Notify::new()),
        }
    }

    pub async fn insert_pending(&self, id: i64) -> oneshot::Receiver<Result<Value, String>> {
        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(id, tx);
        rx
    }

    pub async fn fail_pending(&self, id: i64, reason: String) {
        if let Some(tx) = self.pending.lock().await.remove(&id) {
            let _ = tx.send(Err(reason));
        }
    }

    pub async fn reject_all(&self, reason: &str) {
        let pending = {
            let mut lock = self.pending.lock().await;
            std::mem::take(&mut *lock)
        };
        for (_, tx) in pending {
            let _ = tx.send(Err(reason.to_string()));
        }
    }

    pub fn mark_ready(&self) {
        self.ready.store(true, Ordering::SeqCst);
        self.ready_notify.notify_waiters();
    }

    pub fn reset_ready(&self) {
        self.ready.store(false, Ordering::SeqCst);
    }

    pub fn is_ready(&self) -> bool {
        self.ready.load(Ordering::SeqCst)
    }

    #[allow(dead_code)]
    pub async fn wait_ready(&self, timeout: Duration) -> Result<(), String> {
        if self.is_ready() {
            return Ok(());
        }

        tokio::time::timeout(timeout, async {
            loop {
                if self.is_ready() {
                    return;
                }
                self.ready_notify.notified().await;
            }
        })
        .await
        .map_err(|_| format!("Sidecar ready timeout ({}s)", timeout.as_secs()))
    }

    pub async fn drain_stdout_chunk<F>(&self, chunk: &str, mut on_progress: F)
    where
        F: FnMut(Value),
    {
        let normalized = chunk.replace("\r\n", "\n");
        let mut buffer = self.stdout_buffer.lock().await;
        buffer.push_str(&normalized);
        let mut lines = buffer.split('\n').map(str::to_owned).collect::<Vec<_>>();
        let remainder = lines.pop().unwrap_or_default();
        *buffer = remainder;
        drop(buffer);

        for line in lines {
            self.handle_line(&line, &mut on_progress).await;
        }
    }

    pub async fn flush_stdout<F>(&self, mut on_progress: F)
    where
        F: FnMut(Value),
    {
        let remainder = {
            let mut buffer = self.stdout_buffer.lock().await;
            if buffer.trim().is_empty() {
                buffer.clear();
                return;
            }
            std::mem::take(&mut *buffer)
        };
        self.handle_line(&remainder, &mut on_progress).await;
    }

    async fn handle_line<F>(&self, line: &str, on_progress: &mut F)
    where
        F: FnMut(Value),
    {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            return;
        }

        let parsed: Value = match serde_json::from_str(trimmed) {
            Ok(value) => value,
            Err(_) => {
                eprintln!("[sidecar] failed to parse stdout line: {trimmed}");
                return;
            }
        };

        let Some(obj) = parsed.as_object() else {
            return;
        };

        if let Some(id) = obj.get("id").and_then(Value::as_i64) {
            let result = if let Some(error) = obj.get("error") {
                Err(format_jsonrpc_error(error))
            } else if let Some(result) = obj.get("result") {
                Ok(result.clone())
            } else {
                return;
            };

            if let Some(tx) = self.pending.lock().await.remove(&id) {
                let _ = tx.send(result);
            }
            return;
        }

        match obj.get("method").and_then(Value::as_str) {
            Some("ready") => self.mark_ready(),
            Some("progress") => {
                on_progress(obj.get("params").cloned().unwrap_or_else(|| json!({})));
            }
            _ => {}
        }
    }
}

impl Default for LineProtocol {
    fn default() -> Self {
        Self::new()
    }
}

pub struct SidecarProcess {
    child: Mutex<Option<CommandChild>>,
    protocol: Arc<LineProtocol>,
    terminated: AtomicBool,
}

impl SidecarProcess {
    fn new(child: CommandChild) -> Self {
        Self {
            child: Mutex::new(Some(child)),
            protocol: Arc::new(LineProtocol::new()),
            terminated: AtomicBool::new(false),
        }
    }

    fn is_terminated(&self) -> bool {
        self.terminated.load(Ordering::SeqCst)
    }

    fn mark_terminated(&self) {
        self.terminated.store(true, Ordering::SeqCst);
        self.protocol.reset_ready();
    }
}

pub struct SidecarManager {
    pub binaries_dir: PathBuf,
    pub kuro: Mutex<Option<Arc<SidecarProcess>>>,
    pub mame: Mutex<Option<Arc<SidecarProcess>>>,
    pub next_id: AtomicI64,
    pub app_handle: AppHandle<Wry>,
    kuro_spawn_lock: Mutex<()>,
    mame_spawn_lock: Mutex<()>,
}

impl SidecarManager {
    pub fn new(app: AppHandle<Wry>, binaries_dir: PathBuf) -> Self {
        Self {
            binaries_dir,
            kuro: Mutex::new(None),
            mame: Mutex::new(None),
            next_id: AtomicI64::new(1),
            app_handle: app,
            kuro_spawn_lock: Mutex::new(()),
            mame_spawn_lock: Mutex::new(()),
        }
    }

    pub async fn rpc(&self, kind: &str, method: &str, params: Value) -> Result<Value, String> {
        let process = self.ensure_spawned(kind).await?;
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let rx = process.protocol.insert_pending(id).await;
        let payload = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        let write_result = {
            let mut child = process.child.lock().await;
            let Some(child) = child.as_mut() else {
                process.protocol.fail_pending(id, "Sidecar not running".to_string()).await;
                return Err("Sidecar not running".to_string());
            };
            child.write(format!("{payload}\n").as_bytes())
        };

        if let Err(err) = write_result {
            let message = err.to_string();
            process.protocol.fail_pending(id, message.clone()).await;
            return Err(message);
        }

        match tokio::time::timeout(RPC_TIMEOUT, rx).await {
            Ok(Ok(Ok(value))) => Ok(value),
            Ok(Ok(Err(err))) => Err(format!("{method}: {err}")),
            Ok(Err(_)) => Err("Sidecar response channel closed".to_string()),
            Err(_) => {
                process
                    .protocol
                    .fail_pending(id, format!("RPC timeout: {method} after {}ms", RPC_TIMEOUT.as_millis()))
                    .await;
                Err(format!("RPC timeout: {method} after {}ms", RPC_TIMEOUT.as_millis()))
            }
        }
    }

    pub async fn kill(&self, kind: &str) -> Result<(), String> {
        let slot = self.slot(kind)?;
        let process = slot.lock().await.take();
        if let Some(process) = process {
            process.mark_terminated();
            process.protocol.reject_all("Sidecar killed").await;
            if let Some(child) = process.child.lock().await.take() {
                child.kill().map_err(|err| err.to_string())?;
            }
        }
        Ok(())
    }

    /// §22 Graceful shutdown with 5-second SIGKILL fallback.
    ///
    /// 1. Send `{"jsonrpc":"2.0","id":<n>,"method":"shutdown","params":{}}` over stdin.
    /// 2. Poll `process.is_terminated()` for up to `timeout_secs` seconds.
    /// 3. If the process has not exited, fall back to `kill()`.
    ///
    /// The existing `kill()` command is left unchanged for immediate force-kill
    /// paths (user-initiated cancel, `sidecar_kill` Tauri command).
    pub async fn graceful_kill(&self, kind: &str, timeout_secs: u64) -> Result<(), String> {
        let slot = self.slot(kind)?;
        let process = {
            let lock = slot.lock().await;
            lock.clone()
        };
        let Some(process) = process else {
            return Ok(());
        };
        if process.is_terminated() {
            // Already gone — just clear the slot.
            slot.lock().await.take();
            return Ok(());
        }

        // Send the shutdown RPC over stdin.
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let payload = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": "shutdown",
            "params": {},
        });
        {
            let mut child = process.child.lock().await;
            if let Some(child) = child.as_mut() {
                if let Err(err) = child.write(format!("{payload}\n").as_bytes()) {
                    // Write failure means the process is already exiting — log and proceed to poll.
                    eprintln!("[sidecar:{kind}] shutdown write failed: {err}");
                }
            }
        }

        // Poll for clean exit.
        let poll_result = tokio::time::timeout(
            Duration::from_secs(timeout_secs),
            async {
                loop {
                    if process.is_terminated() {
                        return;
                    }
                    tokio::time::sleep(Duration::from_millis(50)).await;
                }
            },
        )
        .await;

        if poll_result.is_err() {
            eprintln!("[sidecar:{kind}] graceful shutdown timed out after {timeout_secs}s, force-killing");
        }

        // Clear the slot and force-kill if still running.
        let remaining = slot.lock().await.take();
        if let Some(proc) = remaining {
            proc.mark_terminated();
            proc.protocol.reject_all("Sidecar shutdown").await;
            if let Some(child) = proc.child.lock().await.take() {
                let _ = child.kill();
            }
        }
        Ok(())
    }

    pub async fn is_running(&self, kind: &str) -> Result<bool, String> {
        let slot = self.slot(kind)?;
        let process = slot.lock().await.clone();
        Ok(process.is_some_and(|proc| !proc.is_terminated()))
    }

    async fn ensure_spawned(&self, kind: &str) -> Result<Arc<SidecarProcess>, String> {
        // Mirrors legacy kuro behaviour: spawn the child and return immediately.
        // Do NOT block on the ready notification — the host enqueues the RPC on
        // the child stdin and the response comes back once the python main loop
        // starts. Heavy imports (numpy / pandas / biopython) on first launch
        // must not surface as a ready timeout.
        if let Some(existing) = self.current_process(kind).await? {
            return Ok(existing);
        }

        let spawn_lock = self.spawn_lock(kind)?;
        let _guard = spawn_lock.lock().await;

        if let Some(existing) = self.current_process(kind).await? {
            return Ok(existing);
        }

        let process = self.spawn_process(kind).await?;
        let slot = self.slot(kind)?;
        *slot.lock().await = Some(process.clone());
        Ok(process)
    }

    async fn current_process(&self, kind: &str) -> Result<Option<Arc<SidecarProcess>>, String> {
        let slot = self.slot(kind)?;
        let current = slot.lock().await.clone();
        Ok(current.filter(|process| !process.is_terminated()))
    }

    async fn spawn_process(&self, kind: &str) -> Result<Arc<SidecarProcess>, String> {
        let binary_name = binary_name(kind)?;

        // §14 Data Integrity: verify sidecar binary hash before spawning.
        // Skipped entirely in debug builds. In release builds, a mismatch
        // aborts the spawn and surfaces an error to the caller.
        //
        // `self.binaries_dir` is set from `app.path().resource_dir()` in
        // lib.rs and is the correct location for Tauri-bundled resources on
        // all platforms (including macOS where resources live in
        // Contents/Resources/, separate from the Contents/MacOS/ exe dir).
        verify_binary_hash(kind, binary_name, &self.binaries_dir)?;

        let (mut rx, child) = self
            .app_handle
            .shell()
            .sidecar(binary_name)
            .map_err(|err| err.to_string())?
            .spawn()
            .map_err(|err| err.to_string())?;

        let process = Arc::new(SidecarProcess::new(child));
        let process_for_task = process.clone();
        let app_handle = self.app_handle.clone();
        let kind_owned = kind.to_string();

        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(bytes) => {
                        let chunk = String::from_utf8_lossy(&bytes).into_owned();
                        let protocol = process_for_task.protocol.clone();
                        let app = app_handle.clone();
                        let kind = kind_owned.clone();
                        protocol
                            .drain_stdout_chunk(&chunk, move |params| {
                                let payload = SidecarProgressPayload {
                                    kind: kind.clone(),
                                    params,
                                };
                                let _ = app.emit("sidecar://progress", payload);
                            })
                            .await;
                    }
                    CommandEvent::Stderr(bytes) => {
                        let line = String::from_utf8_lossy(&bytes);
                        if !line.trim().is_empty() {
                            eprintln!("[sidecar:{kind_owned}] {line}");
                        }
                    }
                    CommandEvent::Error(error) => {
                        if !error.trim().is_empty() {
                            eprintln!("[sidecar:{kind_owned}] {error}");
                        }
                    }
                    CommandEvent::Terminated(_) => {
                        process_for_task.mark_terminated();
                        process_for_task
                            .protocol
                            .flush_stdout(|_| {})
                            .await;
                        process_for_task
                            .protocol
                            .reject_all("Sidecar process exited")
                            .await;
                        let mut child = process_for_task.child.lock().await;
                        *child = None;
                        break;
                    }
                    _ => {}
                }
            }
        });

        Ok(process)
    }

    fn slot(&self, kind: &str) -> Result<&Mutex<Option<Arc<SidecarProcess>>>, String> {
        match kind {
            "kuro" => Ok(&self.kuro),
            "mame" => Ok(&self.mame),
            _ => Err(format!("Unknown sidecar kind: {kind}")),
        }
    }

    fn spawn_lock(&self, kind: &str) -> Result<&Mutex<()>, String> {
        match kind {
            "kuro" => Ok(&self.kuro_spawn_lock),
            "mame" => Ok(&self.mame_spawn_lock),
            _ => Err(format!("Unknown sidecar kind: {kind}")),
        }
    }
}

fn binary_name(kind: &str) -> Result<&'static str, String> {
    match kind {
        "kuro" => Ok("kuro-sidecar"),
        "mame" => Ok("mame-sidecar"),
        _ => Err(format!("Unknown sidecar kind: {kind}")),
    }
}

/// Verify a sidecar binary hash against the manifest before spawning.
///
/// Path resolution:
/// - Manifest (`sidecar-hashes.json`): loaded from `resource_dir` (the
///   `binaries_dir` field on `SidecarManager`, set via `app.path().resource_dir()`
///   in lib.rs). On macOS this resolves to `App.app/Contents/Resources/`, which
///   is where Tauri places bundled resources — distinct from the exe directory.
/// - Binary: `current_exe().parent() / base_name[.exe]`. Tauri strips the
///   target-triple suffix from externalBin names in release bundles, so on all
///   platforms the binary is found at the bare base name.
///
/// Manifest key lookup priority:
/// 1. `{base_name}-{BUILD_TARGET}{ext}` — e.g. `kuro-sidecar-x86_64-pc-windows-msvc.exe`
///    This is what `scripts/sidecar-hash.mjs` writes for each full filename.
/// 2. `{base_name}{ext}` — e.g. `kuro-sidecar.exe`
///    Fallback for a future hash script that strips the triple suffix.
/// 3. `{base_name}` — e.g. `kuro-sidecar`
///    Legacy/base-key fallback (NOTE: cross-build last-wins; not platform-deterministic).
///
/// In debug builds the function returns `Ok(())` immediately without reading
/// any file, so developers do not need to regenerate hashes on every recompile.
fn verify_binary_hash(
    kind: &str,
    base_name: &str,
    resource_dir: &std::path::Path,
) -> Result<(), String> {
    if cfg!(debug_assertions) {
        return Ok(());
    }

    use crate::sidecar_verify::verify_sidecar;

    // Binary lives next to the app executable (externalBin, triple-suffix stripped).
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .ok_or_else(|| "Cannot resolve current executable directory".to_string())?;

    let ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let binary_path = exe_dir.join(format!("{base_name}{ext}"));

    // Manifest lives in the Tauri resource directory (bundled via tauri.conf.json
    // resources). On macOS: Contents/Resources/. On Linux/Windows: typically
    // the same dir as the exe, but we use resource_dir for correctness.
    let manifest_path = resource_dir.join("sidecar-hashes.json");
    let manifest_bytes = std::fs::read(&manifest_path).map_err(|e| {
        format!(
            "[sidecar:{kind}] Cannot read hash manifest {}: {}",
            manifest_path.display(),
            e
        )
    })?;
    let manifest: serde_json::Map<String, serde_json::Value> =
        serde_json::from_slice(&manifest_bytes).map_err(|e| {
            format!(
                "[sidecar:{kind}] Malformed hash manifest {}: {}",
                manifest_path.display(),
                e
            )
        })?;

    // Build the three candidate keys in priority order:
    //   1. triple-suffixed full key (matches sidecar-hash.mjs output exactly)
    //   2. ext-only key (future-proofing)
    //   3. bare base name (legacy cross-build fallback; not platform-deterministic)
    let build_target = env!("BUILD_TARGET");
    let triple_key = format!("{base_name}-{build_target}{ext}");
    let ext_key = format!("{base_name}{ext}");

    let expected_hash = manifest
        .get(&triple_key)
        .or_else(|| manifest.get(&ext_key))
        .or_else(|| manifest.get(base_name))
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .ok_or_else(|| {
            format!(
                "[sidecar:{kind}] No hash entry for '{triple_key}', '{ext_key}', or '{base_name}' in manifest"
            )
        })?;

    verify_sidecar(&binary_path, expected_hash)
        .map_err(|e| format!("[sidecar:{kind}] {e}"))
}

fn format_jsonrpc_error(error: &Value) -> String {
    let code = error.get("code").and_then(Value::as_i64);
    let message = error
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("Unknown sidecar error");
    match code {
        Some(code) => format!("[{code}] {message}"),
        None => message.to_string(),
    }
}
