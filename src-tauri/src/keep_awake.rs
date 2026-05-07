use std::sync::Mutex;

/// Global KeepAwake handle. Dropped when replaced with `None`.
/// Using `std::sync::Mutex` (not tokio) because KeepAwake is !Send on some platforms.
static AWAKE: Mutex<Option<keepawake::KeepAwake>> = Mutex::new(None);

/// Start OS sleep inhibit. Idempotent: replaces any existing handle.
/// Errors are soft — caller should treat as non-fatal.
#[tauri::command]
pub fn keep_awake_start(reason: String) -> Result<(), String> {
    let ka = keepawake::Builder::default()
        .display(false)
        .idle(true)
        .sleep(true)
        .reason(reason)
        .app_name("KUMA")
        .create()
        .map_err(|e| e.to_string())?;
    *AWAKE.lock().map_err(|e| e.to_string())? = Some(ka);
    Ok(())
}

/// Release the OS sleep inhibit.
/// Safe to call even when no inhibit is active.
#[tauri::command]
pub fn keep_awake_stop() -> Result<(), String> {
    *AWAKE.lock().map_err(|e| e.to_string())? = None;
    Ok(())
}
