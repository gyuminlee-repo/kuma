use kuma_lib::project::{compute_stage, create_project, load_project};
use tempfile::tempdir;

#[test]
fn creates_project_folder_with_schema_v1() {
    let root = tempdir().unwrap();
    let path = create_project(root.path(), "Sample_42").unwrap();
    assert!(path.join("kuma.project.json").exists());
    let proj = load_project(&path).unwrap();
    assert_eq!(proj.schema, 1);
    assert_eq!(proj.name, "Sample_42");
    assert_eq!(proj.stage, "draft");
}

#[test]
fn stage_is_draft_when_no_xlsx() {
    let root = tempdir().unwrap();
    let p = create_project(root.path(), "S").unwrap();
    assert_eq!(compute_stage(&p), "draft");
}

#[test]
fn stage_is_design_complete_when_xlsx_present() {
    let root = tempdir().unwrap();
    let p = create_project(root.path(), "S").unwrap();
    std::fs::write(p.join("design/expected_mutations.xlsx"), b"").unwrap();
    assert_eq!(compute_stage(&p), "design_complete");
}

#[test]
fn stage_is_analyzing_when_consensus_present_without_verdict() {
    let root = tempdir().unwrap();
    let p = create_project(root.path(), "S").unwrap();
    std::fs::write(p.join("analysis/consensus/c1.fa"), b">x\nACGT").unwrap();
    assert_eq!(compute_stage(&p), "analyzing");
}

#[test]
fn stage_is_done_when_verdict_present() {
    let root = tempdir().unwrap();
    let p = create_project(root.path(), "S").unwrap();
    std::fs::write(p.join("analysis/verdict.xlsx"), b"").unwrap();
    assert_eq!(compute_stage(&p), "done");
}

#[test]
fn duplicate_name_gets_numeric_suffix() {
    let root = tempdir().unwrap();
    let p1 = create_project(root.path(), "Sample_42").unwrap();
    let p2 = create_project(root.path(), "Sample_42").unwrap();
    assert_eq!(p1.file_name().unwrap(), "Sample_42");
    assert_eq!(p2.file_name().unwrap(), "Sample_42_2");
}

#[test]
fn load_project_returns_err_on_corrupt_json() {
    let root = tempdir().unwrap();
    let p = root.path().join("broken");
    std::fs::create_dir_all(&p).unwrap();
    std::fs::write(p.join("kuma.project.json"), "{not json").unwrap();
    assert!(load_project(&p).is_err());
}

#[test]
fn load_project_rejects_future_schema() {
    let root = tempdir().unwrap();
    let p = create_project(root.path(), "S").unwrap();
    let mut proj = load_project(&p).unwrap();
    proj.schema = 99;
    std::fs::write(
        p.join("kuma.project.json"),
        serde_json::to_string(&proj).unwrap(),
    )
    .unwrap();
    let err = load_project(&p).unwrap_err();
    assert!(err.contains("SchemaTooNew"));
}
