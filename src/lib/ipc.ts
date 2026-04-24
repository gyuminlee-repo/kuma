import { invoke } from "@tauri-apps/api/core";

export type SidecarKind = "kuro" | "mame";

function hasTauriBridge(): boolean {
  return typeof (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== "undefined";
}

export async function rpc<T = unknown>(
  kind: SidecarKind,
  method: string,
  params: unknown = {},
): Promise<T> {
  if (!hasTauriBridge()) {
    throw new Error("Tauri bridge unavailable");
  }
  return invoke("sidecar_rpc", { kind, method, params }) as Promise<T>;
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
