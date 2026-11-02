//! A13: an interrupted config write must not leave onboarding stuck.

use kuma_lib::config::{load_or_init_config, save_config, set_projects_root, Config};
use std::fs;
use tempfile::tempdir;

const TRUNCATED: &str = "{\n  \"projects_root\": \"/x\",\n  \"recent_";

fn siblings(dir: &std::path::Path) -> Vec<String> {
    let mut names: Vec<String> = fs::read_dir(dir)
        .unwrap()
        .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
        .collect();
    names.sort();
    names
}

#[test]
fn corrupt_config_routes_to_reconfigure() {
    let cfg_root = tempdir().unwrap();
    fs::write(cfg_root.path().join("config.json"), TRUNCATED).unwrap();
    let err = load_or_init_config(cfg_root.path()).unwrap_err();
    assert_eq!(err, "NeedsReconfigure");
}

#[test]
fn choosing_a_folder_recovers_from_corrupt_config_and_keeps_the_damaged_copy() {
    let cfg_root = tempdir().unwrap();
    fs::write(cfg_root.path().join("config.json"), TRUNCATED).unwrap();
    let new_root = tempdir().unwrap();

    let cfg = set_projects_root(cfg_root.path(), new_root.path()).unwrap();
    assert_eq!(cfg.projects_root, new_root.path());
    assert!(cfg.recent_projects.is_empty());
    assert_eq!(
        load_or_init_config(cfg_root.path()).unwrap().projects_root,
        new_root.path()
    );

    let preserved: Vec<String> = siblings(cfg_root.path())
        .into_iter()
        .filter(|n| n.starts_with("config.json.corrupt-"))
        .collect();
    assert_eq!(preserved.len(), 1, "damaged config must be kept: {preserved:?}");
    assert_eq!(
        fs::read_to_string(cfg_root.path().join(&preserved[0])).unwrap(),
        TRUNCATED
    );
}

#[test]
fn save_config_leaves_no_temporary_file_behind() {
    let cfg_root = tempdir().unwrap();
    let cfg = Config {
        projects_root: cfg_root.path().to_path_buf(),
        recent_projects: Vec::new(),
    };
    save_config(cfg_root.path(), &cfg).unwrap();
    save_config(cfg_root.path(), &cfg).unwrap();
    assert_eq!(siblings(cfg_root.path()), vec!["config.json".to_string()]);
}

/// A save cut short inside a multibyte character (a Korean folder name) is
/// invalid UTF-8. It is damage to recover from, the same as truncated JSON.
#[test]
fn choosing_a_folder_recovers_from_a_config_cut_inside_a_multibyte_character() {
    let cfg_root = tempdir().unwrap();
    let mut bytes = "{\n  \"projects_root\": \"/x/프로젝트".as_bytes().to_vec();
    bytes.truncate(bytes.len() - 1);
    assert!(std::str::from_utf8(&bytes).is_err());
    fs::write(cfg_root.path().join("config.json"), &bytes).unwrap();
    assert_eq!(load_or_init_config(cfg_root.path()).unwrap_err(), "NeedsReconfigure");

    let new_root = tempdir().unwrap();
    let cfg = set_projects_root(cfg_root.path(), new_root.path()).unwrap();
    assert_eq!(cfg.projects_root, new_root.path());
    let preserved: Vec<String> = siblings(cfg_root.path())
        .into_iter()
        .filter(|n| n.starts_with("config.json.corrupt-"))
        .collect();
    assert_eq!(preserved.len(), 1, "damaged config must be kept: {preserved:?}");
    assert_eq!(fs::read(cfg_root.path().join(&preserved[0])).unwrap(), bytes);
}
