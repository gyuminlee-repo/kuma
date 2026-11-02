//! A14: a failed export over an existing backup must leave that backup intact.
#![cfg(unix)]

use kuma_lib::project_archive::export_project;
use std::fs::{self, File};
use std::os::unix::fs::PermissionsExt;
use zip::ZipArchive;

#[test]
fn failed_overwrite_keeps_previous_zip() {
    let temp = tempfile::tempdir().unwrap();
    let project = temp.path().join("project");
    fs::create_dir_all(project.join("design")).unwrap();
    fs::write(project.join("kuma.project.json"), "{}").unwrap();
    let locked = project.join("design/locked.json");
    fs::write(&locked, "{\"v\":1}").unwrap();
    let output = temp.path().join("backup.zip");

    let first = export_project(&project, &output).unwrap();
    assert_eq!(first.file_count, 2);
    assert_eq!(first.total_bytes, 2 + 7);
    let before = fs::read(&output).unwrap();

    fs::set_permissions(&locked, fs::Permissions::from_mode(0o000)).unwrap();
    if File::open(&locked).is_ok() {
        eprintln!("skipped: running with privileges that ignore file modes");
        return;
    }
    let second = export_project(&project, &output);
    fs::set_permissions(&locked, fs::Permissions::from_mode(0o600)).unwrap();

    assert!(second.is_err(), "export of an unreadable file must fail");
    assert_eq!(fs::read(&output).unwrap(), before, "previous backup was destroyed");
    assert_eq!(ZipArchive::new(File::open(&output).unwrap()).unwrap().len(), 2);
    let names: Vec<String> = fs::read_dir(temp.path())
        .unwrap()
        .map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
        .collect();
    assert_eq!(names.len(), 2, "temporary ZIP left behind: {names:?}");
}

#[test]
fn export_skips_temporary_debris_inside_the_project() {
    let temp = tempfile::tempdir().unwrap();
    let project = temp.path().join("project");
    fs::create_dir_all(&project).unwrap();
    fs::write(project.join("kuma.project.json"), "{}").unwrap();
    // What a crash during an earlier export into the folder leaves behind.
    fs::write(project.join(".backup.zip.kuma-tmp-1-0"), "partial").unwrap();
    let output = project.join("backup.zip");

    let summary = export_project(&project, &output).unwrap();
    assert_eq!(summary.file_count, 1);
    let mut archive = ZipArchive::new(File::open(&output).unwrap()).unwrap();
    assert_eq!(archive.len(), 1);
    assert!(archive.by_name("kuma.project.json").is_ok());
}
