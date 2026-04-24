pub mod config;
pub mod project;

pub fn run() {
    if let Err(e) = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            config::get_config_cmd,
            config::set_projects_root_cmd,
            config::create_project_cmd,
            config::load_project_cmd,
            config::list_recent_projects_cmd,
        ])
        .run(tauri::generate_context!())
    {
        eprintln!("Fatal: {e}");
        std::process::exit(1);
    }
}
