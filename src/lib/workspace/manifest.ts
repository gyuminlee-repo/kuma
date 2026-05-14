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
  } catch {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as WorkspaceManifest;
    if (parsed.schemaVersion !== SCHEMA_VERSION) return null;
    if (!Array.isArray(parsed.artifacts)) return null;
    return parsed;
  } catch {
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    await rename(path, `${path}.bak-${ts}`).catch(() => {});
    return null;
  }
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
