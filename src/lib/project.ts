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
