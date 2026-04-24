pub mod config;
pub mod project;
pub mod sidecar;

use serde_json::Value;
use std::path::PathBuf;
use tauri::{Manager, State};

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

pub fn run() {
    if let Err(e) = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let binaries_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| PathBuf::from("src-tauri/binaries"));
            app.manage(sidecar::SidecarManager::new(app.handle().clone(), binaries_dir));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            config::get_config_cmd,
            config::set_projects_root_cmd,
            config::create_project_cmd,
            config::load_project_cmd,
            config::list_recent_projects_cmd,
            sidecar_rpc,
            sidecar_kill,
            sidecar_is_running,
        ])
        .run(tauri::generate_context!())
    {
        eprintln!("Fatal: {e}");
        std::process::exit(1);
    }
}
