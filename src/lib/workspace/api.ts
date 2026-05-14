import { stat, exists } from "@tauri-apps/plugin-fs";
import { resolve, isAbsolute } from "@tauri-apps/api/path";
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

const ACTIVE_REGISTRY_LS_KEY = "kuma:artifact-registry:active";

let activeDir: string | null = null;

/**
 * Compute a relative path from base to target via string ops.
 * Returns target unchanged if it does not start with base.
 */
function computeRelative(base: string, target: string): string {
  // Normalise separators to forward-slash for cross-platform consistency
  const normBase = base.replace(/\\/g, "/").replace(/\/$/, "");
  const normTarget = target.replace(/\\/g, "/");
  if (normTarget.startsWith(normBase + "/")) {
    return normTarget.slice(normBase.length + 1);
  }
  return normTarget;
}

async function tryReadPersistedDir(): Promise<string | null> {
  if (typeof localStorage === "undefined") return null;
  try {
    const v = localStorage.getItem(ACTIVE_REGISTRY_LS_KEY);
    if (!v) return null;
    return (await isAbsolute(v)) ? v : null;
  } catch {
    return null;
  }
}

function persistActiveDir(dir: string | null): void {
  if (typeof localStorage === "undefined") return;
  try {
    if (dir) localStorage.setItem(ACTIVE_REGISTRY_LS_KEY, dir);
    else localStorage.removeItem(ACTIVE_REGISTRY_LS_KEY);
  } catch {
    // persistence is best-effort
  }
}

export async function openWorkspace(dir: string): Promise<void> {
  if (!(await isAbsolute(dir))) {
    throw new Error(`workspace dir must be absolute: ${dir}`);
  }
  activeDir = dir;
  persistActiveDir(dir);
  const existing = await readManifest(dir);
  if (!existing) {
    await writeManifest(dir, createEmptyManifest());
  }
  emit("workspace:updated");
}

export async function ensureWorkspaceFromExportPath(absoluteExportPath: string): Promise<void> {
  if (activeDir) return;
  if (!(await isAbsolute(absoluteExportPath))) return;
  const dir = absoluteExportPath.replace(/[\\/][^\\/]*$/, "");
  if (!dir || !(await isAbsolute(dir))) return;
  await openWorkspace(dir);
}

export async function restorePersistedWorkspace(): Promise<boolean> {
  if (activeDir) return true;
  const dir = await tryReadPersistedDir();
  if (!dir) return false;
  if (!(await exists(dir))) {
    persistActiveDir(null);
    return false;
  }
  await openWorkspace(dir);
  return true;
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
    if (!(await exists(it.absolutePath))) {
      throw new Error(`artifact path does not exist: ${it.absolutePath}`);
    }
    const st = await stat(it.absolutePath);
    const rel = computeRelative(dir, it.absolutePath);
    const entry: ManifestArtifact = {
      id: crypto.randomUUID(),
      app: it.app,
      step: it.step,
      type: it.type,
      path: rel,
      producedAt: now,
      mtime: (st.mtime ?? new Date()).toISOString(),
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
    const abs = await resolve(dir, a.path);
    if (!(await exists(abs))) {
      changed = true;
      continue;
    }
    live.push(a);
    if (filter?.app && a.app !== filter.app) continue;
    if (filter?.type && a.type !== filter.type) continue;
    const st = await stat(abs);
    const currentMtime = (st.mtime ?? new Date()).toISOString();
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

