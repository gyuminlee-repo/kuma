use std::collections::HashSet;
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
    #[serde(default)]
    pub project_id: Option<String>,
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

fn expand_home_with(path: &Path, home: Option<PathBuf>) -> PathBuf {
    let Some(raw) = path.to_str() else {
        return path.to_path_buf();
    };
    let Some(home) = home else {
        return path.to_path_buf();
    };
    if raw == "~" {
        return home;
    }
    if let Some(rest) = raw.strip_prefix("~/").or_else(|| raw.strip_prefix("~\\")) {
        return home.join(rest);
    }
    path.to_path_buf()
}

fn expand_home(path: &Path) -> PathBuf {
    expand_home_with(path, dirs::home_dir())
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
    let expanded_root = expand_home(new_root);
    fs::create_dir_all(&expanded_root).map_err(|e| e.to_string())?;
    let mut cfg = match load_or_init_config(config_root) {
        Ok(c) => c,
        Err(e) if e == "NeedsReconfigure" => read_config_file(config_root)?,
        Err(e) => return Err(e),
    };
    cfg.projects_root = expanded_root;
    save_config(config_root, &cfg)?;
    Ok(cfg)
}

pub fn push_recent(config_root: &Path, project_path: &Path, name: &str) -> Result<(), String> {
    let mut cfg = read_config_file(config_root)?;
    let path_str = project_path.to_string_lossy().to_string();
    let project_id = load_project(project_path).ok().map(|proj| proj.project_id);
    cfg.recent_projects.retain(|r| r.path != path_str);
    cfg.recent_projects.insert(
        0,
        RecentProject {
            path: path_str,
            name: name.to_string(),
            last_opened: Local::now().to_rfc3339(),
            project_id,
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

pub(crate) fn prune_missing(projects: Vec<RecentProject>) -> Vec<RecentProject> {
    projects
        .into_iter()
        .filter(|r| Path::new(&r.path).exists())
        .collect()
}

#[tauri::command]
pub fn list_recent_projects_cmd() -> Result<Vec<RecentProject>, String> {
    let root = prod_config_root();
    let mut cfg = load_or_init_config(&root)?;
    let before = cfg.recent_projects.len();
    cfg.recent_projects = prune_missing(cfg.recent_projects);
    if cfg.recent_projects.len() != before {
        save_config(&root, &cfg)?;
    }
    Ok(cfg.recent_projects)
}

/// Resolve `path` to its real location if it is safe to move to the trash.
///
/// Guards run in order and each failure returns a distinct message so the
/// frontend can tell the user which rule blocked the delete.
pub(crate) fn ensure_deletable_with(
    path: &Path,
    projects_root: &Path,
    home: Option<PathBuf>,
) -> Result<PathBuf, String> {
    // (a) must be an existing directory
    if !path.is_dir() {
        return Err("DeleteRefused: path is not an existing directory".into());
    }

    // (b) must be a valid kuma project (kuma.project.json marker)
    load_project(path).map_err(|e| format!("DeleteRefused: not a kuma project folder ({e})"))?;

    // (c) resolved path must not be home, a filesystem root, or projects_root
    let target = path
        .canonicalize()
        .map_err(|e| format!("DeleteRefused: cannot resolve real path ({e})"))?;

    if let Some(home) = home.as_deref().and_then(canonical) {
        if target == home {
            return Err("DeleteRefused: refusing to delete the home directory".into());
        }
        // Equality alone lets an ancestor through: deleting `~/..`-side folders
        // would take the home directory down with them.
        if home.starts_with(&target) {
            return Err("DeleteRefused: refusing to delete a parent of the home directory".into());
        }
    }
    if target.parent().is_none() {
        return Err("DeleteRefused: refusing to delete a filesystem root".into());
    }
    if let Some(root) = canonical(projects_root) {
        if target == root {
            return Err("DeleteRefused: refusing to delete the projects root folder".into());
        }
        // Same ancestor hole: with projects_root at ~/work/thesis/runs, deleting
        // ~/work/thesis would trash every project inside it.
        if root.starts_with(&target) {
            return Err("DeleteRefused: refusing to delete a parent of the projects root".into());
        }
    }

    Ok(target)
}

fn canonical(path: &Path) -> Option<PathBuf> {
    path.canonicalize().ok()
}

fn ensure_deletable(path: &Path, projects_root: &Path) -> Result<PathBuf, String> {
    ensure_deletable_with(path, projects_root, dirs::home_dir())
}

/// Direct children of `projects_root` that are valid projects but absent from `recents`.
pub(crate) fn collect_restorable(
    projects_root: &Path,
    recents: &[RecentProject],
) -> Vec<RecentProject> {
    let Ok(entries) = fs::read_dir(projects_root) else {
        return Vec::new();
    };
    let known: HashSet<PathBuf> = recents.iter().map(|r| PathBuf::from(&r.path)).collect();

    let mut out: Vec<RecentProject> = entries
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir() && !known.contains(p))
        .filter_map(|p| {
            let proj = load_project(&p).ok()?;
            Some(RecentProject {
                path: p.to_string_lossy().to_string(),
                name: proj.name,
                last_opened: String::new(),
                project_id: Some(proj.project_id),
            })
        })
        .collect();

    out.sort_by(|a, b| a.name.cmp(&b.name).then_with(|| a.path.cmp(&b.path)));
    out
}

#[tauri::command]
pub fn list_restorable_projects_cmd() -> Result<Vec<RecentProject>, String> {
    let Ok(cfg) = read_config_file(&prod_config_root()) else {
        return Ok(Vec::new());
    };
    Ok(collect_restorable(&cfg.projects_root, &cfg.recent_projects))
}

#[tauri::command]
pub fn delete_project_folder_cmd(path: String) -> Result<Vec<RecentProject>, String> {
    let root = prod_config_root();
    let mut cfg = read_config_file(&root)?;
    let removed = Path::new(&path);
    // The guard resolves symlinks so its rules cannot be sidestepped, but the
    // resolved path is deliberately not what gets trashed: the trash crate keeps
    // the final component verbatim, so handing it a resolved path would trash the
    // symlink target instead of the entry the confirmation dialog named.
    ensure_deletable(removed, &cfg.projects_root)?;

    // Only drop the recents entry once the folder actually reached the trash,
    // so a failure never leaves an orphaned folder hidden from the user.
    trash::delete(removed).map_err(|e| format!("DeleteFailed: {e}"))?;

    cfg.recent_projects.retain(|r| Path::new(&r.path) != removed);
    save_config(&root, &cfg)?;
    Ok(cfg.recent_projects)
}

#[tauri::command]
pub fn remove_recent_project_cmd(path: String) -> Result<Vec<RecentProject>, String> {
    let root = prod_config_root();
    let mut cfg = read_config_file(&root)?;
    let before = cfg.recent_projects.len();
    cfg.recent_projects.retain(|r| r.path != path);
    if cfg.recent_projects.len() != before {
        save_config(&root, &cfg)?;
    }
    Ok(cfg.recent_projects)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn make_project(path: &str) -> RecentProject {
        RecentProject {
            path: path.to_string(),
            name: "test".to_string(),
            last_opened: "2026-01-01T00:00:00+00:00".to_string(),
            project_id: None,
        }
    }

    #[test]
    fn prune_missing_keeps_existing_removes_absent() {
        let dir = TempDir::new().unwrap();
        let existing = dir.path().join("exists");
        fs::create_dir_all(&existing).unwrap();

        let projects = vec![
            make_project(existing.to_str().unwrap()),
            make_project("/nonexistent/path/that/cannot/exist/xyzzy"),
        ];

        let pruned = prune_missing(projects);
        assert_eq!(pruned.len(), 1);
        assert_eq!(pruned[0].path, existing.to_str().unwrap());
    }

    #[test]
    fn prune_missing_all_present_returns_all() {
        let dir = TempDir::new().unwrap();
        let a = dir.path().join("a");
        let b = dir.path().join("b");
        fs::create_dir_all(&a).unwrap();
        fs::create_dir_all(&b).unwrap();

        let projects = vec![
            make_project(a.to_str().unwrap()),
            make_project(b.to_str().unwrap()),
        ];
        let pruned = prune_missing(projects);
        assert_eq!(pruned.len(), 2);
    }

    #[test]
    fn prune_missing_all_absent_returns_empty() {
        let projects = vec![
            make_project("/no/such/path/aaa"),
            make_project("/no/such/path/bbb"),
        ];
        let pruned = prune_missing(projects);
        assert!(pruned.is_empty());
    }

    // ---- delete guards -------------------------------------------------
    // These exercise the pure guard only. trash::delete is never called from
    // tests so the developer trash folder stays clean.

    #[test]
    fn ensure_deletable_accepts_a_real_project_under_root() {
        let root = TempDir::new().unwrap();
        let proj = create_project(root.path(), "alpha").unwrap();

        let ok = ensure_deletable_with(&proj, root.path(), Some(PathBuf::from("/nonexistent-home")))
            .unwrap();
        assert_eq!(ok, proj.canonicalize().unwrap());
    }

    #[test]
    fn ensure_deletable_rejects_directory_without_project_marker() {
        let root = TempDir::new().unwrap();
        let plain = root.path().join("just-a-folder");
        fs::create_dir_all(&plain).unwrap();

        let err = ensure_deletable_with(&plain, root.path(), None).unwrap_err();
        assert!(
            err.starts_with("DeleteRefused: not a kuma project folder"),
            "unexpected error: {err}"
        );
    }

    #[test]
    fn ensure_deletable_rejects_missing_path() {
        let root = TempDir::new().unwrap();
        let missing = root.path().join("no/such/project");

        let err = ensure_deletable_with(&missing, root.path(), None).unwrap_err();
        assert_eq!(err, "DeleteRefused: path is not an existing directory");
    }

    #[test]
    fn ensure_deletable_rejects_home_directory() {
        let root = TempDir::new().unwrap();
        let proj = create_project(root.path(), "home-lookalike").unwrap();

        let err = ensure_deletable_with(&proj, root.path(), Some(proj.clone())).unwrap_err();
        assert_eq!(err, "DeleteRefused: refusing to delete the home directory");
    }

    #[test]
    fn ensure_deletable_rejects_projects_root_itself() {
        let root = TempDir::new().unwrap();
        let proj = create_project(root.path(), "root-lookalike").unwrap();

        let err = ensure_deletable_with(&proj, &proj, None).unwrap_err();
        assert_eq!(
            err,
            "DeleteRefused: refusing to delete the projects root folder"
        );
    }

    #[test]
    fn ensure_deletable_rejects_a_parent_of_the_projects_root() {
        // projects_root sits inside the folder being deleted, so trashing the
        // folder would take every project with it.
        let base = TempDir::new().unwrap();
        let thesis = create_project(base.path(), "thesis").unwrap();
        let runs = thesis.join("runs");
        fs::create_dir_all(&runs).unwrap();

        let err = ensure_deletable_with(&thesis, &runs, None).unwrap_err();
        assert_eq!(
            err,
            "DeleteRefused: refusing to delete a parent of the projects root"
        );
    }

    #[test]
    fn ensure_deletable_rejects_a_parent_of_the_home_directory() {
        let base = TempDir::new().unwrap();
        let workspace = create_project(base.path(), "workspace").unwrap();
        let home = workspace.join("home");
        fs::create_dir_all(&home).unwrap();

        let err = ensure_deletable_with(&workspace, base.path(), Some(home)).unwrap_err();
        assert_eq!(
            err,
            "DeleteRefused: refusing to delete a parent of the home directory"
        );
    }

    // ---- restorable listing --------------------------------------------

    #[test]
    fn collect_restorable_excludes_recents_and_non_projects() {
        let root = TempDir::new().unwrap();
        let known = create_project(root.path(), "known").unwrap();
        let forgotten = create_project(root.path(), "forgotten").unwrap();
        fs::create_dir_all(root.path().join("not-a-project")).unwrap();

        let recents = vec![make_project(known.to_str().unwrap())];
        let found = collect_restorable(root.path(), &recents);

        assert_eq!(found.len(), 1);
        assert_eq!(found[0].path, forgotten.to_string_lossy());
        assert_eq!(found[0].name, "forgotten");
        assert_eq!(found[0].last_opened, "");
        assert!(found[0].project_id.is_some());
    }

    #[test]
    fn collect_restorable_sorts_by_name() {
        let root = TempDir::new().unwrap();
        create_project(root.path(), "charlie").unwrap();
        create_project(root.path(), "alpha").unwrap();
        create_project(root.path(), "bravo").unwrap();

        let names: Vec<String> = collect_restorable(root.path(), &[])
            .into_iter()
            .map(|r| r.name)
            .collect();
        assert_eq!(names, vec!["alpha", "bravo", "charlie"]);
    }

    #[test]
    fn collect_restorable_returns_empty_when_root_missing() {
        let root = TempDir::new().unwrap();
        let missing = root.path().join("gone");

        assert!(collect_restorable(&missing, &[]).is_empty());
    }

    #[test]
    fn expand_home_with_expands_home_prefix() {
        let home = PathBuf::from("/tmp/kuma-home");

        assert_eq!(
            expand_home_with(Path::new("~/kuma-test"), Some(home.clone())),
            home.join("kuma-test")
        );
        assert_eq!(expand_home_with(Path::new("~"), Some(home.clone())), home);
        assert_eq!(
            expand_home_with(
                Path::new("/tmp/kuma-test"),
                Some(PathBuf::from("/home/user"))
            ),
            PathBuf::from("/tmp/kuma-test")
        );
    }
}
