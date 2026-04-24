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
