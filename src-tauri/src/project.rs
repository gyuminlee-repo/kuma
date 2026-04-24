use std::fs;
use std::path::{Path, PathBuf};

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
    let path = unique_folder(root, name);
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

fn unique_folder(root: &Path, name: &str) -> PathBuf {
    let candidate = root.join(name);
    if !candidate.exists() {
        return candidate;
    }

    let mut suffix = 2;
    loop {
        let candidate = root.join(format!("{name}_{suffix}"));
        if !candidate.exists() {
            return candidate;
        }
        suffix += 1;
    }
}
