use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter};

pub struct PtySession {
    pub writer: Box<dyn Write + Send>,
    pub master: Box<dyn MasterPty + Send>,
    pub child: Box<dyn Child + Send + Sync>,
}

#[derive(Default)]
pub struct PtyState {
    pub sessions: Mutex<HashMap<u32, PtySession>>,
    pub next_id: AtomicU32,
}

#[tauri::command]
pub async fn pty_spawn(
    app: AppHandle,
    state: tauri::State<'_, PtyState>,
    shell: Option<String>,
    cwd: Option<String>,
    cols: u16,
    rows: u16,
) -> Result<u32, String> {
    let shell_path = if cfg!(target_os = "windows") {
        shell.unwrap_or_else(|| {
            // Prefer pwsh.exe (PowerShell 7+) if on PATH; fall back to powershell.exe (5.1, always present on Win10+).
            let pwsh_found = std::process::Command::new("where")
                .arg("pwsh.exe")
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false);
            if pwsh_found { "pwsh.exe".into() } else { "powershell.exe".into() }
        })
    } else {
        shell.unwrap_or_else(|| std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".into()))
    };

    let pty_system = native_pty_system();
    let pair = pty_system
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;

    let mut cmd = CommandBuilder::new(&shell_path);
    cmd.env("TERM", "xterm-256color");
    #[cfg(target_os = "windows")]
    {
        cmd.env("PYTHONIOENCODING", "utf-8");
    }
    if let Some(dir) = cwd {
        cmd.cwd(dir);
    }

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| e.to_string())?;

    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
    let mut reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;

    let session_id = state.next_id.fetch_add(1, Ordering::SeqCst);

    let app_clone = app.clone();
    tokio::task::spawn_blocking(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    let s = String::from_utf8_lossy(&buf[..n]).to_string();
                    app_clone
                        .emit(
                            "pty://output",
                            serde_json::json!({ "session_id": session_id, "data": s }),
                        )
                        .ok();
                }
                Err(_) => break,
            }
        }
    });

    let session = PtySession {
        writer,
        master: pair.master,
        child,
    };

    state
        .sessions
        .lock()
        .map_err(|e| e.to_string())?
        .insert(session_id, session);

    Ok(session_id)
}

#[tauri::command]
pub fn pty_write(
    state: tauri::State<'_, PtyState>,
    session_id: u32,
    data: String,
) -> Result<(), String> {
    let mut map = state.sessions.lock().map_err(|e| e.to_string())?;
    let session = map
        .get_mut(&session_id)
        .ok_or_else(|| format!("session {} not found", session_id))?;
    session
        .writer
        .write_all(data.as_bytes())
        .map_err(|e| e.to_string())?;
    session.writer.flush().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn pty_resize(
    state: tauri::State<'_, PtyState>,
    session_id: u32,
    cols: u16,
    rows: u16,
) -> Result<(), String> {
    let map = state.sessions.lock().map_err(|e| e.to_string())?;
    let session = map
        .get(&session_id)
        .ok_or_else(|| format!("session {} not found", session_id))?;
    session
        .master
        .resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn pty_kill(state: tauri::State<'_, PtyState>, session_id: u32) -> Result<(), String> {
    let mut map = state.sessions.lock().map_err(|e| e.to_string())?;
    if let Some(mut session) = map.remove(&session_id) {
        session.child.kill().ok();
    }
    Ok(())
}
