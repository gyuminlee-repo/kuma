pub mod config;
pub mod project;
pub mod sidecar;

use serde_json::Value;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent, Wry};

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
    let _ = manager.kill("kuro").await;
    let _ = manager.kill("mame").await;
}

pub fn run() {
    let app = match tauri::Builder::default()
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
        .on_window_event(|window, event| {
            // Only the main window controls app lifecycle.
            // Popovers/dropdowns/dialog plugin windows must not kill sidecars.
            if window.label() != "main" {
                return;
            }
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let app_handle = window.app_handle().clone();
                tauri::async_runtime::spawn(async move {
                    eprintln!("[lifecycle] main CloseRequested → killing sidecars");
                    shutdown_sidecars_async(&app_handle).await;
                    eprintln!("[lifecycle] sidecars killed → exiting app");
                    app_handle.exit(0);
                });
            }
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
