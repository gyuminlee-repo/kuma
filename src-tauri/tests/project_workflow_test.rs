//! End-to-end Rust integration: project lifecycle across stages + recent persistence.
//!
//! Covers Task 10 Step 10.1 flow at the Rust layer:
//! 1. `create_project` under a fresh projects_root → folder + schema v1.
//! 2. `compute_stage` transitions draft → design_complete → analyzing → done
//!    as expected artifacts land in the project folder.
//! 3. Config persistence: `push_recent` records the project; reloading the
//!    config file recovers name + project_id.
//!
//! Uses `tempfile::tempdir` for both config_root and projects_root to avoid
//! touching `~/.kuma`. No Tauri runtime needed — exercises `kuma_lib` API.

use kuma_lib::config::{
    load_or_init_config, push_recent, save_config, set_projects_root, Config,
};
use kuma_lib::project::{compute_stage, create_project, load_project};
use std::fs;
use tempfile::tempdir;

#[test]
fn full_project_lifecycle_stage_transitions() {
    let projects_root = tempdir().unwrap();

    // Step 1: create project → draft.
    let path = create_project(projects_root.path(), "Sample_42").unwrap();
    assert!(path.join("kuma.project.json").exists());
    assert!(path.join("design").exists());
    assert!(path.join("analysis/consensus").exists());
    assert_eq!(compute_stage(&path), "draft");

    // Step 2: design export lands → design_complete.
    fs::write(path.join("design/expected_mutations.xlsx"), b"xlsx").unwrap();
    assert_eq!(compute_stage(&path), "design_complete");

    // Step 3: consensus fasta appears → analyzing.
    fs::write(path.join("analysis/consensus/mock.fasta"), b">x\nACGT").unwrap();
    assert_eq!(compute_stage(&path), "analyzing");

    // Step 4: verdict produced → done.
    fs::write(path.join("analysis/verdict.xlsx"), b"xlsx").unwrap();
    assert_eq!(compute_stage(&path), "done");

    // Schema + name round-trip.
    let proj = load_project(&path).unwrap();
    assert_eq!(proj.schema, 1);
    assert_eq!(proj.name, "Sample_42");
}

#[test]
fn recent_projects_round_trip_through_config_file() {
    let config_root = tempdir().unwrap();
    let projects_root = tempdir().unwrap();

    // Initialize config and point it at our tempdir projects_root.
    let cfg = set_projects_root(config_root.path(), projects_root.path()).unwrap();
    assert_eq!(cfg.projects_root, projects_root.path());
    assert!(cfg.recent_projects.is_empty());

    // Create two projects and register them as recent.
    let p1 = create_project(projects_root.path(), "Alpha").unwrap();
    let p2 = create_project(projects_root.path(), "Beta").unwrap();
    push_recent(config_root.path(), &p1, "Alpha").unwrap();
    push_recent(config_root.path(), &p2, "Beta").unwrap();

    // Reload and assert ordering (most recent first) + project_id attached.
    let reloaded: Config = load_or_init_config(config_root.path()).unwrap();
    assert_eq!(reloaded.recent_projects.len(), 2);
    assert_eq!(reloaded.recent_projects[0].name, "Beta");
    assert_eq!(reloaded.recent_projects[1].name, "Alpha");
    assert!(reloaded.recent_projects[0].project_id.is_some());
    assert!(reloaded.recent_projects[1].project_id.is_some());

    // Recent entries point at real project folders with valid manifests.
    for recent in &reloaded.recent_projects {
        let proj = load_project(std::path::Path::new(&recent.path)).unwrap();
        assert_eq!(proj.schema, 1);
        assert_eq!(Some(proj.project_id), recent.project_id);
    }
}

#[test]
fn push_recent_dedupes_and_reorders() {
    let config_root = tempdir().unwrap();
    let projects_root = tempdir().unwrap();
    set_projects_root(config_root.path(), projects_root.path()).unwrap();

    let p1 = create_project(projects_root.path(), "One").unwrap();
    let p2 = create_project(projects_root.path(), "Two").unwrap();

    push_recent(config_root.path(), &p1, "One").unwrap();
    push_recent(config_root.path(), &p2, "Two").unwrap();
    // Reopen "One" → should move to the front without duplicating.
    push_recent(config_root.path(), &p1, "One").unwrap();

    let cfg = load_or_init_config(config_root.path()).unwrap();
    assert_eq!(cfg.recent_projects.len(), 2);
    assert_eq!(cfg.recent_projects[0].name, "One");
    assert_eq!(cfg.recent_projects[1].name, "Two");
}

#[test]
fn missing_projects_root_surfaces_needs_reconfigure() {
    let config_root = tempdir().unwrap();
    let ghost = config_root.path().join("vanished");

    // Write a config pointing to a non-existent projects_root, then reload.
    let bad = Config {
        projects_root: ghost,
        recent_projects: Vec::new(),
    };
    save_config(config_root.path(), &bad).unwrap();

    let err = load_or_init_config(config_root.path()).unwrap_err();
    assert!(err.contains("NeedsReconfigure"), "expected NeedsReconfigure, got {err}");
}
