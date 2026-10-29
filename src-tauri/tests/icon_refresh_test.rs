use std::fs;
use std::path::{Path, PathBuf};

use kuma_lib::icon_refresh::{
    app_bundle_from_exe, appimage_icon_targets, read_marker, should_refresh, write_marker,
};
use tempfile::tempdir;

#[test]
fn first_run_without_a_marker_refreshes() {
    assert!(should_refresh(None, "0.16.82"));
}

#[test]
fn same_version_does_not_refresh() {
    assert!(!should_refresh(Some("0.16.82"), "0.16.82"));
    // A trailing newline written by hand must not count as a new version.
    assert!(!should_refresh(Some("0.16.82\n"), "0.16.82"));
}

#[test]
fn changed_version_refreshes() {
    assert!(should_refresh(Some("0.16.81"), "0.16.82"));
}

#[test]
fn marker_round_trips_and_creates_its_directory() {
    let root = tempdir().unwrap();
    let marker = root.path().join("nested").join("last_run_version");
    assert_eq!(read_marker(&marker), None);
    write_marker(&marker, "0.16.82").unwrap();
    assert_eq!(read_marker(&marker).as_deref(), Some("0.16.82"));
    assert!(!should_refresh(read_marker(&marker).as_deref(), "0.16.82"));
}

#[test]
fn bundle_path_comes_from_the_executable_inside_an_app() {
    let exe = Path::new("/Applications/kuma.app/Contents/MacOS/kuma");
    assert_eq!(
        app_bundle_from_exe(exe),
        Some(PathBuf::from("/Applications/kuma.app"))
    );
}

#[test]
fn executable_outside_an_app_bundle_has_no_bundle() {
    // `tauri dev` runs target/debug/kuma, which is not inside any .app.
    assert_eq!(app_bundle_from_exe(Path::new("/repo/src-tauri/target/debug/kuma")), None);
    // Contents/MacOS layout without the .app extension is not a bundle either.
    assert_eq!(app_bundle_from_exe(Path::new("/x/kuma/Contents/MacOS/kuma")), None);
}

struct Layout {
    _root: tempfile::TempDir,
    applications: PathBuf,
    icons: PathBuf,
    appdir: PathBuf,
    appimage: PathBuf,
}

const ID: &str = "0123456789abcdef0123456789abcdef";

fn layout() -> Layout {
    let root = tempdir().unwrap();
    let applications = root.path().join("share/applications");
    let icons = root.path().join("share/icons");
    let appdir = root.path().join("mnt/.mount_kuma");
    let appimage = root.path().join("Apps/kuma.AppImage");
    fs::create_dir_all(&applications).unwrap();
    for size in ["32x32", "128x128"] {
        let bundled = appdir.join(format!("usr/share/icons/hicolor/{size}/apps"));
        fs::create_dir_all(&bundled).unwrap();
        fs::write(bundled.join("kuma.png"), b"new").unwrap();
        fs::create_dir_all(icons.join(format!("hicolor/{size}/apps"))).unwrap();
    }
    Layout { _root: root, applications, icons, appdir, appimage }
}

fn integrate(l: &Layout, id: &str, appimage: &Path) {
    fs::write(
        l.applications.join(format!("appimagekit_{id}-kuma.desktop")),
        format!("[Desktop Entry]\nName=kuma\nExec={} %U\nIcon=appimagekit_{id}_kuma\n", appimage.display()),
    )
    .unwrap();
    for size in ["32x32", "128x128"] {
        fs::write(
            l.icons.join(format!("hicolor/{size}/apps/appimagekit_{id}_kuma.png")),
            b"old",
        )
        .unwrap();
    }
}

#[test]
fn integrated_icons_of_this_appimage_are_targeted() {
    let l = layout();
    integrate(&l, ID, &l.appimage);
    let mut targets = appimage_icon_targets(&l.applications, &l.icons, &l.appimage, &l.appdir, "kuma");
    targets.sort();
    let expected: Vec<(PathBuf, PathBuf)> = ["128x128", "32x32"]
        .iter()
        .map(|s| {
            (
                l.appdir.join(format!("usr/share/icons/hicolor/{s}/apps/kuma.png")),
                l.icons.join(format!("hicolor/{s}/apps/appimagekit_{ID}_kuma.png")),
            )
        })
        .collect();
    assert_eq!(targets, expected);
}

#[test]
fn no_desktop_integration_means_no_targets() {
    let l = layout();
    assert!(appimage_icon_targets(&l.applications, &l.icons, &l.appimage, &l.appdir, "kuma").is_empty());
    // A missing applications directory is the same as no integration.
    let gone = l.applications.join("missing");
    assert!(appimage_icon_targets(&gone, &l.icons, &l.appimage, &l.appdir, "kuma").is_empty());
}

#[test]
fn files_of_other_appimages_are_left_alone() {
    let l = layout();
    // Another AppImage at a different path, integrated under its own id.
    let other_id = "fedcba9876543210fedcba9876543210";
    integrate(&l, other_id, &l.appimage.with_file_name("other.AppImage"));
    // An icon carrying this id but another app's name.
    fs::write(l.icons.join(format!("hicolor/32x32/apps/appimagekit_{ID}_other.png")), b"x").unwrap();
    assert!(appimage_icon_targets(&l.applications, &l.icons, &l.appimage, &l.appdir, "kuma").is_empty());
}

#[test]
fn an_integrated_size_the_bundle_lacks_is_skipped() {
    let l = layout();
    integrate(&l, ID, &l.appimage);
    fs::remove_file(l.appdir.join("usr/share/icons/hicolor/128x128/apps/kuma.png")).unwrap();
    let targets = appimage_icon_targets(&l.applications, &l.icons, &l.appimage, &l.appdir, "kuma");
    assert_eq!(targets.len(), 1);
    assert!(targets[0].1.ends_with(format!("hicolor/32x32/apps/appimagekit_{ID}_kuma.png")));
}
