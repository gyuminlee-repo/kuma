import { invoke } from "@tauri-apps/api/core";

export type SidecarKind = "kuro" | "mame";

function hasTauriBridge(): boolean {
  return typeof (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== "undefined";
}

export async function rpc<T = unknown>(
  kind: SidecarKind,
  method: string,
  params: unknown = {},
  timeoutMs?: number,
): Promise<T> {
  if (!hasTauriBridge()) {
    throw new Error("Tauri bridge unavailable");
  }
  return invoke("sidecar_rpc", {
    kind,
    method,
    params,
    timeoutMs: timeoutMs ?? null,
  }) as Promise<T>;
}

export async function killSidecar(kind: SidecarKind): Promise<void> {
  if (!hasTauriBridge()) {
    return;
  }
  await invoke("sidecar_kill", { kind });
}

export async function isSidecarRunning(kind: SidecarKind): Promise<boolean> {
  if (!hasTauriBridge()) {
    return false;
  }
  return invoke("sidecar_is_running", { kind }) as Promise<boolean>;
}

// `classifyRound` used to live here. It is a MAME call, and this module is the
// raw transport both sidecars share, so placing it here sent it to the sidecar
// without passing the MAME client and its result was cast to
// `ClassifyRoundResult` with nothing checking it. It now lives beside every
// other MAME call in `src/lib/ipc-mame/index.ts`, on the validated path.
