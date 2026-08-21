/**
 * MOCK_MODE shim for `@tauri-apps/api/core`.
 *
 * Without this stub `getConfig()` rejects during bootstrap and App.tsx pins the
 * screen to "onboarding", so every capture came out as the folder picker. The
 * stub answers the project-shell commands with plausible values and leaves the
 * rest to the caller's own error handling.
 *
 * It deliberately does NOT compute anything: capture screens receive real
 * sidecar output through the store (see scripts/gen_real_capture_data.py), so
 * `sidecar_rpc` here only has to not throw.
 */

import realDataJson from "../real-data.json";

export interface MockProject {
  path: string;
  name: string;
  last_opened: string;
  project_id?: string | null;
}

// Shown verbatim in captured screenshots, so it stays machine-neutral.
const PROJECT_ROOT = "~/Documents/kuma";
const PROJECT: MockProject = {
  path: `${PROJECT_ROOT}/ispS_evolvepro_round1`,
  name: "ispS_evolvepro_round1",
  last_opened: "2026-08-21T09:00:00+09:00",
  project_id: "00000000-0000-4000-8000-000000000000",
};

const CONFIG = {
  projects_root: PROJECT_ROOT,
  recent_projects: [PROJECT],
};

/**
 * Replies the real sidecar gave for the capture inputs, keyed by RPC method.
 * Loaded lazily so a missing bundle degrades to an empty reply rather than
 * breaking the dev server for every other MOCK_MODE consumer.
 */
type RealBundle = Record<string, unknown>;
// Static import: Vite transforms JSON into a module here. A dynamic
// `import(..., { with: { type: "json" } })` is rejected by the browser MIME
// check under the dev server and silently leaves the bundle empty.
const realBundle = realDataJson as RealBundle;

const SIDECAR_REPLIES: Record<string, (params?: unknown) => unknown> = {
  list_polymerases: () => realBundle.polymerases ?? [],
  load_fasta: () => realBundle.seq_info ?? {},
  load_evolvepro_csv: () => realBundle.evolvepro ?? {},
  preview_evolvepro_source: () => realBundle.evolvepro_preview ?? {},
  design_sdm_primers: () => realBundle.design ?? {},
  get_plate_map: () => realBundle.plate ?? { mappings: [] },
  search_uniprot: () => realBundle.uniprot ?? { candidates: [] },
  fetch_domains: () => realBundle.domains ?? { domains: [] },
  fetch_pdb_text: () => realBundle.pdb_text ?? {},
  check_structures_available: () => realBundle.structures ?? {},
  fetch_active_site_residues: () =>
    realBundle.active_site ?? { accession: "", active_site_positions: [], binding_positions: [] },
  list_organisms: () => realBundle.organisms ?? [],
  export_echo_mapping_dry_run: () => realBundle.echo_dry_run ?? {},
  export_janus_mapping_dry_run: () => realBundle.janus_dry_run ?? {},
  health_info: () => realBundle.health ?? {},
  settings_load: () => realBundle.settings ?? {},
  get_polymerase_details: (params) => {
    const table = (realBundle.polymerase_details ?? {}) as Record<string, unknown>;
    const name = String((params as { name?: unknown } | undefined)?.name ?? "");
    return table[name] ?? {};
  },
  ping: () => ({ ok: true }),
};

/**
 * `rawSidecarRpc` in src/lib/ipc.ts refuses to send unless this marker exists,
 * so without it every panel renders "Tauri bridge unavailable". The plugin
 * wrappers additionally reach for `transformCallback` while registering event
 * channels, so the marker carries a working one rather than an empty object.
 */
let callbackId = 0;
const callbacks = new Map<number, (payload: unknown) => void>();
(globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ ??= {
  transformCallback(callback?: (payload: unknown) => void, _once = false): number {
    callbackId += 1;
    if (callback) callbacks.set(callbackId, callback);
    return callbackId;
  },
  invoke,
  convertFileSrc,
};

const HANDLERS: Record<string, (args?: Record<string, unknown>) => unknown> = {
  get_config_cmd: () => CONFIG,
  set_projects_root_cmd: () => CONFIG,
  list_recent_projects_cmd: () => CONFIG.recent_projects,
  list_restorable_projects_cmd: () => [],
  remove_recent_project_cmd: () => CONFIG.recent_projects,
  create_project_cmd: () => PROJECT.path,
  load_project_cmd: () => ({
    schema: 1,
    project_id: PROJECT.project_id,
    name: PROJECT.name,
    stage: "draft",
  }),
  probe_writable_dir: () => true,
  read_text_head: () => "",
  sidecar_is_running: () => true,
  sidecar_kill: () => null,
  sidecar_rpc: (args) => {
    const method = String(args?.method ?? "");
    const reply = SIDECAR_REPLIES[method];
    if (!reply) {
      // Shouted to the console as well as thrown: the app catches this and
      // paints it into a status bar, where it would ride into a screenshot
      // unnoticed. capture-real.ts watches the console and fails the run.
      const message = `MOCK_MODE: no recorded sidecar reply for "${method}"`;
      console.error(message);
      throw new Error(message);
    }
    return reply(args?.params);
  },
  keep_awake_start: () => null,
  keep_awake_stop: () => null,
  // The sidecar hook subscribes to shell events while spawning. Nothing ever
  // emits in MOCK_MODE, so registering is enough and unlisten is a no-op.
  "plugin:event|listen": () => callbackId,
  "plugin:event|unlisten": () => null,
  "plugin:event|emit": () => null,
  "plugin:event|emit_to": () => null,
};

export async function invoke<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  const handler = HANDLERS[command];
  if (!handler) {
    throw new Error(`MOCK_MODE: no stub for Tauri command "${command}"`);
  }
  return handler(args) as T;
}

export function convertFileSrc(filePath: string): string {
  return filePath;
}

// The fs, notification and updater plugins import these three names from
// api/core at module load. Aliasing api/core without them breaks the bundle
// before a single screen renders, so they exist here as inert shapes.

export class Channel<T = unknown> {
  id = 0;
  onmessage: (message: T) => void = () => {};
  toJSON(): string {
    return `__CHANNEL__:${this.id}`;
  }
}

export class Resource {
  readonly rid: number;
  constructor(rid = 0) {
    this.rid = rid;
  }
  async close(): Promise<void> {
    /* nothing to release in MOCK_MODE */
  }
}

export async function addPluginListener<T>(
  _plugin: string,
  _event: string,
  _cb: (payload: T) => void,
): Promise<{ unregister: () => Promise<void> }> {
  return { unregister: async () => {} };
}

export function isTauri(): boolean {
  return true;
}
