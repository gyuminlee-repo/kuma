//! Project folder <-> zip archive. Lets a project be carried to another machine.
//!
//! The project folder is already self-contained for the things that matter:
//! autosave snapshots live in `.autosave/`, generated artifacts are routed into
//! the folder, and the workspace manifest stores artifact paths relative to it.
//! Autosave snapshots store their own input paths relative to the folder too
//! (see `src/lib/projectPath.ts`). So carrying the folder carries the work.
//!
//! What is left is packing and unpacking it, which is what this module does.
//!
//! Inputs that live outside the project folder (a MinKNOW raw run directory, for
//! instance) are deliberately not pulled in. They are large, and the analysis
//! results derived from them are already persisted inside the folder, so the
//! receiving machine can read results, export, and report without them.

use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};

use serde::Serialize;
use zip::write::SimpleFileOptions;
use zip::{ZipArchive, ZipWriter};

/// Marker file that identifies a project folder. Refuse archives without it.
const PROJECT_MARKER: &str = "kuma.project.json";

#[derive(Serialize, Debug, Clone)]
pub struct ArchiveSummary {
    /// Absolute path of the archive that was written, or the folder produced.
    pub path: String,
    pub file_count: usize,
    pub total_bytes: u64,
}

/// Collect every file under `root`, returning paths relative to `root`.
fn collect_files(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let entries = fs::read_dir(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
        for entry in entries {
            let entry = entry.map_err(|e| e.to_string())?;
            let path = entry.path();
            let meta = entry.metadata().map_err(|e| e.to_string())?;
            if meta.is_dir() {
                stack.push(path);
            } else if meta.is_file() {
                let rel = path
                    .strip_prefix(root)
                    .map_err(|e| e.to_string())?
                    .to_path_buf();
                out.push(rel);
            }
            // Symlinks are skipped: following them would silently pull in data
            // from outside the project folder.
        }
    }
    out.sort();
    Ok(out)
}

/// Normalise a relative path to forward slashes so archives move between OSes.
fn to_archive_name(rel: &Path) -> String {
    rel.components()
        .map(|c| c.as_os_str().to_string_lossy().to_string())
        .collect::<Vec<_>>()
        .join("/")
}

pub fn export_project(project_path: &Path, output_path: &Path) -> Result<ArchiveSummary, String> {
    if !project_path.join(PROJECT_MARKER).is_file() {
        return Err(format!(
            "not a kuma project folder (no {PROJECT_MARKER}): {}",
            project_path.display()
        ));
    }
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let files = collect_files(project_path)?;
    let file = File::create(output_path).map_err(|e| e.to_string())?;
    let mut zip = ZipWriter::new(file);
    // Deflate: these are JSON, xlsx and fasta files, so it pays for itself.
    let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    let mut total_bytes = 0u64;
    let mut buf = Vec::new();
    for rel in &files {
        let abs = project_path.join(rel);
        let mut src = File::open(&abs).map_err(|e| format!("{}: {e}", abs.display()))?;
        buf.clear();
        src.read_to_end(&mut buf).map_err(|e| e.to_string())?;
        zip.start_file(to_archive_name(rel), options)
            .map_err(|e| e.to_string())?;
        zip.write_all(&buf).map_err(|e| e.to_string())?;
        total_bytes += buf.len() as u64;
    }
    zip.finish().map_err(|e| e.to_string())?;

    Ok(ArchiveSummary {
        path: output_path.to_string_lossy().to_string(),
        file_count: files.len(),
        total_bytes,
    })
}

/// Reject archive entries that would escape the destination directory.
///
/// A zip entry name is attacker-controlled data even when the archive came from
/// a colleague, so absolute paths, `..` and Windows path prefixes are refused
/// rather than sanitised. Sanitising invites a near miss; refusing does not.
fn safe_relative(name: &str) -> Result<PathBuf, String> {
    if name.is_empty() {
        return Err("archive entry has an empty name".into());
    }
    let raw = Path::new(name);
    let mut out = PathBuf::new();
    for component in raw.components() {
        match component {
            Component::Normal(part) => out.push(part),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(format!("unsafe path in archive: {name}"));
            }
        }
    }
    if out.as_os_str().is_empty() {
        return Err(format!("archive entry resolves to nothing: {name}"));
    }
    Ok(out)
}

/// Unpack `archive_path` into a new folder under `dest_parent`.
///
/// Returns the folder that was created. The caller opens it as a project.
pub fn import_project(archive_path: &Path, dest_parent: &Path) -> Result<ArchiveSummary, String> {
    let file = File::open(archive_path).map_err(|e| e.to_string())?;
    let mut archive = ZipArchive::new(file).map_err(|e| e.to_string())?;

    // Validate before writing anything. A partially unpacked folder that turns
    // out not to be a project is worse than a clean refusal.
    let mut has_marker = false;
    let mut planned: Vec<(usize, PathBuf)> = Vec::new();
    for i in 0..archive.len() {
        let entry = archive.by_index(i).map_err(|e| e.to_string())?;
        if entry.is_dir() {
            continue;
        }
        let rel = safe_relative(entry.name())?;
        if rel == Path::new(PROJECT_MARKER) {
            has_marker = true;
        }
        planned.push((i, rel));
    }
    if !has_marker {
        return Err(format!(
            "archive is not a kuma project export (no {PROJECT_MARKER} at its root)"
        ));
    }

    let stem = archive_path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "kuma-project".to_string());
    let dest = crate::project::unique_folder(dest_parent, &stem);
    fs::create_dir_all(&dest).map_err(|e| e.to_string())?;

    let mut total_bytes = 0u64;
    for (index, rel) in &planned {
        let mut entry = archive.by_index(*index).map_err(|e| e.to_string())?;
        let target = dest.join(rel);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut out = File::create(&target).map_err(|e| format!("{}: {e}", target.display()))?;
        let written = std::io::copy(&mut entry, &mut out).map_err(|e| e.to_string())?;
        total_bytes += written;
    }

    Ok(ArchiveSummary {
        path: dest.to_string_lossy().to_string(),
        file_count: planned.len(),
        total_bytes,
    })
}

#[tauri::command]
pub fn export_project_zip_cmd(
    project_path: String,
    output_path: String,
) -> Result<ArchiveSummary, String> {
    export_project(Path::new(&project_path), Path::new(&output_path))
}

#[tauri::command]
pub fn import_project_zip_cmd(
    archive_path: String,
    dest_parent: String,
) -> Result<ArchiveSummary, String> {
    import_project(Path::new(&archive_path), Path::new(&dest_parent))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write as _;

    fn write(path: &Path, body: &str) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        let mut f = File::create(path).unwrap();
        f.write_all(body.as_bytes()).unwrap();
    }

    fn make_project(root: &Path) -> PathBuf {
        let project = root.join("run7");
        write(&project.join(PROJECT_MARKER), "{\"schema\":1}");
        write(&project.join(".autosave/kuro.json"), "{\"schema\":3}");
        write(&project.join("design/primers.xlsx"), "xlsx-bytes");
        project
    }

    #[test]
    fn round_trip_preserves_files() {
        let tmp = tempfile::tempdir().unwrap();
        let project = make_project(tmp.path());
        let archive = tmp.path().join("run7.kumaproj.zip");

        let exported = export_project(&project, &archive).unwrap();
        assert_eq!(exported.file_count, 3);

        let dest = tmp.path().join("incoming");
        fs::create_dir_all(&dest).unwrap();
        let imported = import_project(&archive, &dest).unwrap();
        let out = PathBuf::from(&imported.path);

        assert_eq!(imported.file_count, 3);
        assert!(out.join(PROJECT_MARKER).is_file());
        // The autosave snapshot must survive: it is the restored work.
        assert_eq!(
            fs::read_to_string(out.join(".autosave/kuro.json")).unwrap(),
            "{\"schema\":3}"
        );
        assert_eq!(
            fs::read_to_string(out.join("design/primers.xlsx")).unwrap(),
            "xlsx-bytes"
        );
    }

    #[test]
    fn export_refuses_a_folder_that_is_not_a_project() {
        let tmp = tempfile::tempdir().unwrap();
        let plain = tmp.path().join("plain");
        write(&plain.join("notes.txt"), "hi");

        let err = export_project(&plain, &tmp.path().join("out.zip")).unwrap_err();
        assert!(err.contains(PROJECT_MARKER), "{err}");
    }

    #[test]
    fn import_refuses_an_archive_without_the_project_marker() {
        let tmp = tempfile::tempdir().unwrap();
        let archive = tmp.path().join("stray.zip");
        {
            let mut zip = ZipWriter::new(File::create(&archive).unwrap());
            zip.start_file("notes.txt", SimpleFileOptions::default())
                .unwrap();
            zip.write_all(b"hi").unwrap();
            zip.finish().unwrap();
        }

        let err = import_project(&archive, tmp.path()).unwrap_err();
        assert!(err.contains(PROJECT_MARKER), "{err}");
    }

    #[test]
    fn import_refuses_entries_that_escape_the_destination() {
        let tmp = tempfile::tempdir().unwrap();
        let archive = tmp.path().join("evil.zip");
        {
            let mut zip = ZipWriter::new(File::create(&archive).unwrap());
            zip.start_file(PROJECT_MARKER, SimpleFileOptions::default())
                .unwrap();
            zip.write_all(b"{}").unwrap();
            zip.start_file("../escaped.txt", SimpleFileOptions::default())
                .unwrap();
            zip.write_all(b"pwned").unwrap();
            zip.finish().unwrap();
        }

        let dest = tmp.path().join("incoming");
        fs::create_dir_all(&dest).unwrap();
        let err = import_project(&archive, &dest).unwrap_err();
        assert!(err.contains("unsafe path"), "{err}");
        // Nothing may be written when validation fails.
        assert!(!tmp.path().join("escaped.txt").exists());
    }

    #[test]
    fn safe_relative_rejects_absolute_and_parent_paths() {
        assert!(safe_relative("../x").is_err());
        assert!(safe_relative("/etc/passwd").is_err());
        assert!(safe_relative("a/../../b").is_err());
        assert!(safe_relative("").is_err());
        assert_eq!(safe_relative("a/b.txt").unwrap(), PathBuf::from("a/b.txt"));
        assert_eq!(safe_relative("./a.txt").unwrap(), PathBuf::from("a.txt"));
    }

    #[test]
    fn import_does_not_overwrite_an_existing_folder() {
        let tmp = tempfile::tempdir().unwrap();
        let project = make_project(tmp.path());
        let archive = tmp.path().join("run7.zip");
        export_project(&project, &archive).unwrap();

        let dest = tmp.path().join("incoming");
        fs::create_dir_all(&dest).unwrap();
        let first = import_project(&archive, &dest).unwrap();
        let second = import_project(&archive, &dest).unwrap();

        assert_ne!(first.path, second.path);
    }
}
