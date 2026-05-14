import { readFile, writeFile, rename, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { WorkspaceManifest } from "./types";
import { SCHEMA_VERSION, MANIFEST_FILENAME } from "./types";

export function createEmptyManifest(): WorkspaceManifest {
  const now = new Date().toISOString();
  return {
    schemaVersion: SCHEMA_VERSION,
    workspaceId: randomUUID(),
    createdAt: now,
    updatedAt: now,
    artifacts: [],
  };
}

export async function readManifest(dir: string): Promise<WorkspaceManifest | null> {
  const path = join(dir, MANIFEST_FILENAME);
  if (!existsSync(path)) return null;
  let raw: string;
  try {
    raw = await readFile(path, "utf-8");
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
  const path = join(dir, MANIFEST_FILENAME);
  m.updatedAt = new Date().toISOString();
  await writeFile(path, JSON.stringify(m, null, 2), "utf-8");
}

export async function listBackups(dir: string): Promise<string[]> {
  const entries = await readdir(dir);
  return entries.filter((f) => f.startsWith(`${MANIFEST_FILENAME}.bak-`));
}
