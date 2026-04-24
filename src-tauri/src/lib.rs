pub mod project;

pub fn run() {
    if let Err(e) = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .run(tauri::generate_context!())
    {
        eprintln!("Fatal: {e}");
        std::process::exit(1);
    }
}
