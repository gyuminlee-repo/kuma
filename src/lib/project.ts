import { invoke } from "@tauri-apps/api/core";

export interface RecentProject {
  path: string;
  name: string;
  last_opened: string;
  project_id?: string | null;
}

export interface Config {
  projects_root: string;
  recent_projects: RecentProject[];
}

export interface Project {
  schema: number;
  project_id: string;
  name: string;
  stage?: string;
  [key: string]: unknown;
}

export async function getConfig(): Promise<Config> {
  return invoke<Config>("get_config_cmd");
}

export async function setProjectsRoot(path: string): Promise<Config> {
  return invoke<Config>("set_projects_root_cmd", { path });
}

export async function createProject(name: string): Promise<string> {
  return invoke<string>("create_project_cmd", { name });
}

export async function loadProject(path: string): Promise<Project> {
  return invoke<Project>("load_project_cmd", { path });
}

export async function listRecentProjects(): Promise<RecentProject[]> {
  return invoke<RecentProject[]>("list_recent_projects_cmd");
}

/**
 * List-only removal: drops the entry from the recent list while the folder
 * stays on disk. Returns the updated recent list, mirroring
 * `deleteProjectFolder` so both removal paths have the same shape.
 */
export async function removeRecentProject(path: string): Promise<RecentProject[]> {
  return invoke<RecentProject[]>("remove_recent_project_cmd", { path });
}

/**
 * Projects that live under the projects root but are absent from the recent
 * list, i.e. entries removed from the list while their folder stayed on disk.
 * `last_opened` is unknown for these and comes back as an empty string.
 */
export async function listRestorableProjects(): Promise<RecentProject[]> {
  return invoke<RecentProject[]>("list_restorable_projects_cmd");
}

/**
 * Moves the project folder to the OS trash (never a permanent delete) and
 * removes it from the recent list. Returns the updated recent list.
 */
export async function deleteProjectFolder(path: string): Promise<RecentProject[]> {
  return invoke<RecentProject[]>("delete_project_folder_cmd", { path });
}

/** export_project_zip_cmd / import_project_zip_cmd 결과. */
export interface ArchiveSummary {
  /** 내보낸 zip 경로, 또는 가져오기로 만들어진 프로젝트 폴더 경로. */
  path: string;
  file_count: number;
  total_bytes: number;
}

/**
 * 프로젝트 폴더를 zip 하나로 묶는다. 다른 PC로 옮겨 이어서 작업하기 위한 통로다.
 *
 * 폴더 밖 대용량 입력(MinKNOW raw run 등)은 담지 않는다. 분석 결과가 이미 폴더
 * 안에 보존돼 있어 받는 쪽에서 결과 조회·내보내기·리포트가 모두 가능하다.
 */
export async function exportProjectZip(
  projectPath: string,
  outputPath: string,
): Promise<ArchiveSummary> {
  return invoke<ArchiveSummary>("export_project_zip_cmd", { projectPath, outputPath });
}

/** zip 을 `destParent` 아래 새 폴더로 풀고 그 경로를 돌려준다. */
export async function importProjectZip(
  archivePath: string,
  destParent: string,
): Promise<ArchiveSummary> {
  return invoke<ArchiveSummary>("import_project_zip_cmd", { archivePath, destParent });
}
