import { open, save } from "@tauri-apps/plugin-dialog";
import { readTextFile, writeTextFile } from "@tauri-apps/plugin-fs";
import { buildWorkspaceDefaultPath } from "../filename";
import type { KumaProject } from "../../state/projectContext";
import type { InputMode, RawRunParams } from "@/store/mame/slice-interfaces";

export interface WorkspaceSnapshot {
  version: 1;
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  mode: "amplicon" | "plasmid";
  ingestMode: "barcode" | "amplicon";
  // R6 additions (optional for backwards-compat with v1 snapshots).
  inputMode?: InputMode;
  rawRunParams?: RawRunParams;
  cdsStart: number;
  cdsEnd: number;
  minFileSizeKb: number;
  manyCutoff: number;
}

const WORKSPACE_FILTER = [{ name: "mame workspace", extensions: ["mame.json", "json"] }];

export async function saveWorkspaceToFile(
  snapshot: WorkspaceSnapshot,
  project: KumaProject,
): Promise<string | null> {
  const path = await save({
    filters: WORKSPACE_FILTER,
    defaultPath: buildWorkspaceDefaultPath(project, "mame"),
  });
  if (!path) return null;
  await writeTextFile(path, JSON.stringify(snapshot, null, 2));
  return path;
}

export async function loadWorkspaceFromFile(project: KumaProject): Promise<WorkspaceSnapshot | null> {
  const defaultPath =
    project && !project.scratch && project.path ? project.path : undefined;
  const selected = await open({ multiple: false, filters: WORKSPACE_FILTER, defaultPath });
  const path = typeof selected === "string" ? selected : null;
  if (!path) return null;
  const text = await readTextFile(path);
  const parsed = JSON.parse(text) as Partial<WorkspaceSnapshot>;
  if (parsed.version !== 1) {
    throw new Error(`Unsupported workspace version: ${String(parsed.version)}`);
  }
  return parsed as WorkspaceSnapshot;
}
