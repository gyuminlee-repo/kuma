import {
  readTextFile,
  writeTextFile,
  rename,
  readDir,
  exists,
} from "@tauri-apps/plugin-fs";
import { join } from "@tauri-apps/api/path";
import type { WorkspaceManifest } from "./types";
import { SCHEMA_VERSION, MANIFEST_FILENAME } from "./types";

export function createEmptyManifest(): WorkspaceManifest {
  const now = new Date().toISOString();
  return {
    schemaVersion: SCHEMA_VERSION,
    workspaceId: crypto.randomUUID(),
    createdAt: now,
    updatedAt: now,
    artifacts: [],
  };
}

export async function readManifest(dir: string): Promise<WorkspaceManifest | null> {
  const path = await join(dir, MANIFEST_FILENAME);
  if (!(await exists(path))) return null;
  let raw: string;
  try {
    raw = await readTextFile(path);
  } catch (error) {
    throw new Error(`Workspace manifest could not be read: ${path}: ${String(error)}`);
  }

  let parsed: WorkspaceManifest;
  try {
    parsed = JSON.parse(raw) as WorkspaceManifest;
  } catch (error) {
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    try {
      await rename(path, `${path}.bak-${ts}`);
    } catch (renameError) {
      throw new Error(`Workspace manifest is invalid and could not be preserved: ${path}: ${String(renameError)}`);
    }
    throw new Error(`Workspace manifest is invalid and was preserved as a backup: ${path}: ${String(error)}`);
  }
  if (parsed.schemaVersion !== SCHEMA_VERSION) {
    throw new Error(`Workspace manifest schema is unsupported: ${path}`);
  }
  if (!Array.isArray(parsed.artifacts)) {
    throw new Error(`Workspace manifest artifacts are invalid: ${path}`);
  }
  return parsed;
}

export async function writeManifest(dir: string, m: WorkspaceManifest): Promise<void> {
  const path = await join(dir, MANIFEST_FILENAME);
  m.updatedAt = new Date().toISOString();
  await writeTextFile(path, JSON.stringify(m, null, 2));
}

export async function listBackups(dir: string): Promise<string[]> {
  const entries = await readDir(dir);
  return entries
    .filter((e) => e.name.startsWith(`${MANIFEST_FILENAME}.bak-`))
    .map((e) => e.name);
}
