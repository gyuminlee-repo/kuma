use kuma_lib::project_archive::{export_project_zip_cmd, import_project_zip_cmd};
use std::fs::{self, File};
use zip::ZipArchive;

#[test]
fn repeated_exports_inside_project_restore_only_project_files() {
    exercise_export(true);
}

#[test]
fn repeated_exports_outside_project_restore_only_project_files() {
    exercise_export(false);
}

fn exercise_export(internal: bool) {
    let temp = tempfile::tempdir().unwrap();
    let project = temp.path().join("project");
    fs::create_dir_all(project.join(".autosave")).unwrap();
    fs::write(project.join("kuma.project.json"), "{}").unwrap();
    fs::write(project.join(".autosave/kuro.json"), "{\"value\":42}").unwrap();
    let output = if internal {
        project.join("backup.zip")
    } else {
        temp.path().join("backup.zip")
    };
    for _ in 0..3 {
        let summary = export_project_zip_cmd(
            project.to_string_lossy().into_owned(),
            output.to_string_lossy().into_owned(),
        )
        .unwrap();
        assert_eq!(summary.file_count, 2);
        let mut archive = ZipArchive::new(File::open(&output).unwrap()).unwrap();
        assert_eq!(archive.len(), 2);
        assert!(archive.by_name("backup.zip").is_err());
        let restored = import_project_zip_cmd(
            output.to_string_lossy().into_owned(),
            temp.path().join("restored").to_string_lossy().into_owned(),
        )
        .unwrap();
        assert_eq!(
            fs::read(std::path::Path::new(&restored.path).join(".autosave/kuro.json")).unwrap(),
            b"{\"value\":42}"
        );
    }
}
