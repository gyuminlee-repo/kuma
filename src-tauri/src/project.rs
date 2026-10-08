use std::ffi::OsStr;
use std::fs;
use std::path::{Component, Path, PathBuf};

use chrono::Local;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Project {
    pub schema: u32,
    pub project_id: String,
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    pub stage: String,
    pub kuro_workspace: Option<String>,
    pub expected_mutations: Option<String>,
    pub analysis_input: Option<String>,
    pub analysis_output: Option<String>,
    pub last_opened_tab: String,
}

pub fn create_project(root: &Path, name: &str) -> Result<PathBuf, String> {
    let path = unique_folder(root, name)?;
    fs::create_dir_all(path.join("design")).map_err(|e| e.to_string())?;
    fs::create_dir_all(path.join("analysis/consensus")).map_err(|e| e.to_string())?;

    let now = Local::now().to_rfc3339();
    let project = Project {
        schema: 1,
        project_id: Uuid::new_v4().to_string(),
        name: name.to_string(),
        created_at: now.clone(),
        updated_at: now,
        stage: "draft".to_string(),
        kuro_workspace: None,
        expected_mutations: None,
        analysis_input: None,
        analysis_output: None,
        last_opened_tab: "kuro".to_string(),
    };

    let json = serde_json::to_string_pretty(&project).map_err(|e| e.to_string())?;
    fs::write(path.join("kuma.project.json"), json).map_err(|e| e.to_string())?;

    Ok(path)
}

pub fn load_project(path: &Path) -> Result<Project, String> {
    let json = fs::read_to_string(path.join("kuma.project.json")).map_err(|e| e.to_string())?;
    let proj: Project = serde_json::from_str(&json).map_err(|e| e.to_string())?;

    if proj.schema > 1 {
        return Err("SchemaTooNew".into());
    }

    Ok(proj)
}

pub fn compute_stage(path: &Path) -> String {
    let has_xlsx = path.join("design/expected_mutations.xlsx").exists();
    // Consider the consensus directory meaningful only if it contains at least
    // one non-hidden entry whose metadata we can read. This avoids .DS_Store
    // style OS bookkeeping or unreadable entries flipping the stage.
    let consensus_has_files = fs::read_dir(path.join("analysis/consensus"))
        .map(|entries| {
            entries.flatten().any(|e| {
                e.file_name()
                    .to_str()
                    .map(|n| !n.starts_with('.'))
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false);
    let has_verdict = path.join("analysis/verdict.xlsx").exists();

    match (has_xlsx, consensus_has_files, has_verdict) {
        (_, _, true) => "done",
        (_, true, false) => "analyzing",
        (true, false, false) => "design_complete",
        _ => "draft",
    }
    .to_string()
}

/// Reject a folder name that would not land directly inside its root.
///
/// The name reaching here is data: `create_project_cmd` passes whatever the UI
/// typed, and `import_project` passes an archive filename. `Path::join` treats
/// such a string as a path, so `../escaped` climbs out of the root and an
/// absolute path replaces it outright, and the folder is created wherever the
/// string pointed.
///
/// `project_archive::safe_relative` refuses the same three shapes for zip
/// entries, and its rule is the right one: refuse, never sanitise, because a
/// sanitised name is a near miss that looks like it worked. Its SHAPE does not
/// fit here, though. It accepts a multi-component relative path (`a/b.txt`),
/// which is correct for a file inside an archive and wrong for a folder name,
/// where `a/b` would silently create a nested pair and put the project one level
/// below where every other path in the app expects it. So the rule is the same
/// and the check is narrower: exactly one `Component::Normal`, spelled the way
/// it was given.
pub(crate) fn safe_folder_name(name: &str) -> Result<&str, String> {
    if name.is_empty() {
        return Err("project name cannot be empty".into());
    }
    let mut components = Path::new(name).components();
    match (components.next(), components.next()) {
        // The equality guard catches everything `components()` normalises away:
        // a trailing separator, `./name`, a repeated separator. Each of those is
        // a name the operator did not type, and quietly accepting the cleaned-up
        // form is the sanitising this refuses to do.
        (Some(Component::Normal(part)), None) if part == OsStr::new(name) => Ok(name),
        _ => Err(format!(
            "project name must be a single folder name, with no path separators, \
             no '..' and no drive letter: {name:?}"
        )),
    }
}

/// Pick a folder name that does not collide, appending `_2`, `_3`, ... as needed.
///
/// Validates the name first. The check lives here rather than in each caller
/// because this is the function that turns a name into a path: a caller that
/// checked for itself would protect only itself, and the next one added would
/// not.
pub(crate) fn unique_folder(root: &Path, name: &str) -> Result<PathBuf, String> {
    let name = safe_folder_name(name)?;
    let candidate = root.join(name);
    if !candidate.exists() {
        return Ok(candidate);
    }

    let mut suffix = 2;
    loop {
        let candidate = root.join(format!("{name}_{suffix}"));
        if !candidate.exists() {
            return Ok(candidate);
        }
        suffix += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::MAIN_SEPARATOR;

    #[test]
    fn safe_folder_name_accepts_an_ordinary_name() {
        assert_eq!(safe_folder_name("alpha").unwrap(), "alpha");
        assert_eq!(safe_folder_name("2026-08 run 3").unwrap(), "2026-08 run 3");
        // A dot inside a name is a name, not a traversal.
        assert_eq!(safe_folder_name("v1.2").unwrap(), "v1.2");
    }

    #[test]
    fn safe_folder_name_refuses_anything_that_is_a_path() {
        for bad in ["../escaped", "..", ".", "a/b", "a/../../b", ""] {
            assert!(safe_folder_name(bad).is_err(), "accepted {bad:?}");
        }
        assert!(safe_folder_name("/abs/path").is_err());
        assert!(safe_folder_name(&format!("alpha{MAIN_SEPARATOR}")).is_err());
    }

    #[test]
    fn unique_folder_refuses_a_name_that_would_leave_the_root() {
        let root = Path::new("/tmp/kuma-projects");
        assert!(unique_folder(root, "../escaped").is_err());
        // `Path::join` discards the root entirely on an absolute component, so
        // this used to return the caller's own path unchanged.
        assert!(unique_folder(root, "/etc").is_err());
        assert_eq!(
            unique_folder(root, "alpha").unwrap(),
            root.join("alpha"),
        );
    }

    #[test]
    fn create_project_refuses_a_traversing_name() {
        let root = std::env::temp_dir().join(format!(
            "kuma-project-guard-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let err = create_project(&root, "../escaped").unwrap_err();
        assert!(err.contains("single folder name"), "{err}");
        assert!(!root.parent().unwrap().join("escaped").exists());
        let _ = fs::remove_dir_all(&root);
    }
}
