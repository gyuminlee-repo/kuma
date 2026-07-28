use kuma_lib::config::{load_or_init_config, push_recent, save_config, set_projects_root, Config};
use tempfile::tempdir;

#[test]
fn creates_default_config_on_first_run() {
    let cfg_root = tempdir().unwrap();
    let cfg = load_or_init_config(cfg_root.path()).unwrap();
    assert!(cfg.projects_root.ends_with("kuma"));
    assert!(cfg.recent_projects.is_empty());
    assert!(cfg_root.path().join("config.json").exists());
}

#[test]
fn second_load_returns_same_config() {
    let cfg_root = tempdir().unwrap();
    let first = load_or_init_config(cfg_root.path()).unwrap();
    let second = load_or_init_config(cfg_root.path()).unwrap();
    assert_eq!(first.projects_root, second.projects_root);
}

#[test]
fn needs_reconfigure_when_projects_root_missing() {
    let cfg_root = tempdir().unwrap();
    let stale = tempdir().unwrap();
    let stale_path = stale.path().to_path_buf();
    drop(stale);
    let cfg = Config {
        projects_root: stale_path,
        recent_projects: Vec::new(),
    };
    save_config(cfg_root.path(), &cfg).unwrap();
    let err = load_or_init_config(cfg_root.path()).unwrap_err();
    assert_eq!(err, "NeedsReconfigure");
}

#[test]
fn set_projects_root_updates_config() {
    let cfg_root = tempdir().unwrap();
    let _ = load_or_init_config(cfg_root.path()).unwrap();
    let new_root = tempdir().unwrap();
    let cfg = set_projects_root(cfg_root.path(), new_root.path()).unwrap();
    assert_eq!(cfg.projects_root, new_root.path());
    let reloaded = load_or_init_config(cfg_root.path()).unwrap();
    assert_eq!(reloaded.projects_root, new_root.path());
}

#[test]
fn set_projects_root_recovers_from_needs_reconfigure() {
    let cfg_root = tempdir().unwrap();
    let stale = tempdir().unwrap();
    let stale_path = stale.path().to_path_buf();
    drop(stale);
    let cfg = Config {
        projects_root: stale_path,
        recent_projects: Vec::new(),
    };
    save_config(cfg_root.path(), &cfg).unwrap();
    let new_root = tempdir().unwrap();
    let recovered = set_projects_root(cfg_root.path(), new_root.path()).unwrap();
    assert_eq!(recovered.projects_root, new_root.path());
}

#[test]
fn push_recent_deduplicates_and_orders_most_recent_first() {
    let cfg_root = tempdir().unwrap();
    let _ = load_or_init_config(cfg_root.path()).unwrap();
    let a = tempdir().unwrap();
    let b = tempdir().unwrap();
    push_recent(cfg_root.path(), a.path(), "A").unwrap();
    push_recent(cfg_root.path(), b.path(), "B").unwrap();
    push_recent(cfg_root.path(), a.path(), "A").unwrap();
    let cfg = load_or_init_config(cfg_root.path()).unwrap();
    assert_eq!(cfg.recent_projects.len(), 2);
    assert_eq!(cfg.recent_projects[0].name, "A");
    assert_eq!(cfg.recent_projects[1].name, "B");
}
