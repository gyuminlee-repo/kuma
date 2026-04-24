use std::fs;
use std::path::{Path, PathBuf};

use chrono::Local;
use serde::{Deserialize, Serialize};

use crate::project::{create_project, load_project, Project};

const CONFIG_FILENAME: &str = "config.json";
const MAX_RECENT: usize = 20;

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct RecentProject {
    pub path: String,
    pub name: String,
    pub last_opened: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Config {
    pub projects_root: PathBuf,
    pub recent_projects: Vec<RecentProject>,
}

fn default_projects_root() -> PathBuf {
    dirs::document_dir()
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_else(|| PathBuf::from(".")))
        .join("kuma")
}

fn config_file(config_root: &Path) -> PathBuf {
    config_root.join(CONFIG_FILENAME)
}

fn prod_config_root() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".kuma")
}

fn read_config_file(config_root: &Path) -> Result<Config, String> {
    let text = fs::read_to_string(config_file(config_root)).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

pub fn save_config(config_root: &Path, cfg: &Config) -> Result<(), String> {
    fs::create_dir_all(config_root).map_err(|e| e.to_string())?;
    let json = serde_json::to_string_pretty(cfg).map_err(|e| e.to_string())?;
    fs::write(config_file(config_root), json).map_err(|e| e.to_string())
}

pub fn load_or_init_config(config_root: &Path) -> Result<Config, String> {
    fs::create_dir_all(config_root).map_err(|e| e.to_string())?;
    let path = config_file(config_root);
    if !path.exists() {
        let root = default_projects_root();
        fs::create_dir_all(&root).map_err(|e| e.to_string())?;
        let cfg = Config {
            projects_root: root,
            recent_projects: Vec::new(),
        };
        save_config(config_root, &cfg)?;
        return Ok(cfg);
    }
    let cfg = read_config_file(config_root)?;
    if !cfg.projects_root.exists() {
        return Err("NeedsReconfigure".into());
    }
    Ok(cfg)
}

pub fn set_projects_root(config_root: &Path, new_root: &Path) -> Result<Config, String> {
    fs::create_dir_all(new_root).map_err(|e| e.to_string())?;
    let mut cfg = match load_or_init_config(config_root) {
        Ok(c) => c,
        Err(e) if e == "NeedsReconfigure" => read_config_file(config_root)?,
        Err(e) => return Err(e),
    };
    cfg.projects_root = new_root.to_path_buf();
    save_config(config_root, &cfg)?;
    Ok(cfg)
}

pub fn push_recent(config_root: &Path, project_path: &Path, name: &str) -> Result<(), String> {
    let mut cfg = read_config_file(config_root)?;
    let path_str = project_path.to_string_lossy().to_string();
    cfg.recent_projects.retain(|r| r.path != path_str);
    cfg.recent_projects.insert(
        0,
        RecentProject {
            path: path_str,
            name: name.to_string(),
            last_opened: Local::now().to_rfc3339(),
        },
    );
    if cfg.recent_projects.len() > MAX_RECENT {
        cfg.recent_projects.drain(MAX_RECENT..);
    }
    save_config(config_root, &cfg)
}

// ----------------- Tauri commands -----------------

#[tauri::command]
pub fn get_config_cmd() -> Result<Config, String> {
    load_or_init_config(&prod_config_root())
}

#[tauri::command]
pub fn set_projects_root_cmd(path: String) -> Result<Config, String> {
    set_projects_root(&prod_config_root(), Path::new(&path))
}

#[tauri::command]
pub fn create_project_cmd(name: String) -> Result<String, String> {
    let root = prod_config_root();
    let cfg = load_or_init_config(&root)?;
    let project_path = create_project(&cfg.projects_root, &name)?;
    let _ = push_recent(&root, &project_path, &name);
    Ok(project_path.to_string_lossy().to_string())
}

#[tauri::command]
pub fn load_project_cmd(path: String) -> Result<Project, String> {
    let p = Path::new(&path);
    let proj = load_project(p)?;
    let _ = push_recent(&prod_config_root(), p, &proj.name);
    Ok(proj)
}

#[tauri::command]
pub fn list_recent_projects_cmd() -> Result<Vec<RecentProject>, String> {
    let cfg = load_or_init_config(&prod_config_root())?;
    Ok(cfg.recent_projects)
}
