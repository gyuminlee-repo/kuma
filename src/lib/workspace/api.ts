import { randomUUID } from "node:crypto";
import { stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { relative, resolve, isAbsolute } from "node:path";
import { readManifest, writeManifest, createEmptyManifest } from "./manifest";
import { emit } from "./events";
import type {
  AppId,
  ArtifactType,
  ArtifactRef,
  NewArtifact,
  ManifestArtifact,
  WorkspaceManifest,
} from "./types";

let activeDir: string | null = null;

export async function openWorkspace(dir: string): Promise<void> {
  if (!isAbsolute(dir)) {
    throw new Error(`workspace dir must be absolute: ${dir}`);
  }
  activeDir = dir;
  const existing = await readManifest(dir);
  if (!existing) {
    await writeManifest(dir, createEmptyManifest());
  }
  emit("workspace:updated");
}

export function getActiveWorkspace(): string | null {
  return activeDir;
}

export function _resetWorkspaceForTest(): void {
  activeDir = null;
}

function requireDir(): string {
  if (!activeDir) throw new Error("workspace not opened");
  return activeDir;
}

function key(a: { app: AppId; step: string; type: ArtifactType }): string {
  return `${a.app}::${a.step}::${a.type}`;
}

async function loadOrCreate(dir: string): Promise<WorkspaceManifest> {
  return (await readManifest(dir)) ?? createEmptyManifest();
}

export async function registerArtifacts(items: NewArtifact[]): Promise<void> {
  if (items.length === 0) return;
  const dir = requireDir();
  const m = await loadOrCreate(dir);
  const now = new Date().toISOString();
  for (const it of items) {
    if (!existsSync(it.absolutePath)) {
      throw new Error(`artifact path does not exist: ${it.absolutePath}`);
    }
    const st = await stat(it.absolutePath);
    const rel = relative(dir, it.absolutePath);
    const entry: ManifestArtifact = {
      id: randomUUID(),
      app: it.app,
      step: it.step,
      type: it.type,
      path: rel,
      producedAt: now,
      mtime: new Date(st.mtimeMs).toISOString(),
      sizeBytes: st.size,
    };
    m.artifacts = m.artifacts.filter((a) => key(a) !== key(entry));
    m.artifacts.push(entry);
  }
  await writeManifest(dir, m);
  emit("workspace:updated");
}

export async function listArtifacts(
  filter?: { app?: AppId; type?: ArtifactType },
): Promise<ArtifactRef[]> {
  const dir = requireDir();
  const m = await loadOrCreate(dir);
  const live: ManifestArtifact[] = [];
  const refs: ArtifactRef[] = [];
  let changed = false;
  for (const a of m.artifacts) {
    const abs = resolve(dir, a.path);
    if (!existsSync(abs)) {
      changed = true;
      continue;
    }
    live.push(a);
    if (filter?.app && a.app !== filter.app) continue;
    if (filter?.type && a.type !== filter.type) continue;
    const st = await stat(abs);
    const currentMtime = new Date(st.mtimeMs).toISOString();
    refs.push({ ...a, path: abs, stale: currentMtime !== a.mtime });
  }
  if (changed) {
    m.artifacts = live;
    await writeManifest(dir, m);
    emit("workspace:updated");
  }
  return refs;
}

export async function getLatestArtifact(
  type: ArtifactType,
): Promise<ArtifactRef | null> {
  const items = await listArtifacts({ type });
  if (items.length === 0) return null;
  return items.sort((a, b) => b.producedAt.localeCompare(a.producedAt))[0];
}

export async function clearWorkspace(appId: AppId): Promise<void> {
  const dir = requireDir();
  const m = await loadOrCreate(dir);
  const before = m.artifacts.length;
  m.artifacts = m.artifacts.filter((a) => a.app !== appId);
  if (m.artifacts.length !== before) {
    await writeManifest(dir, m);
    emit("workspace:updated");
  }
}
