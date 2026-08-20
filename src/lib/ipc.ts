import { invoke } from "@tauri-apps/api/core";

export type SidecarKind = "kuro" | "mame";

function hasTauriBridge(): boolean {
  return typeof (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== "undefined";
}

/**
 * Raw sidecar transport. NOT the function to call from feature code.
 *
 * It sends a method name and params to a sidecar and casts the reply to `T`
 * with nothing checking that the reply is a `T`. That cast is the whole problem:
 * a payload of the wrong shape becomes `undefined` deep inside a component
 * rather than an error at the boundary.
 *
 * The guarded entry points are `sendRequest` in `src/lib/ipc-kuro/index.ts` and
 * `src/lib/ipc-mame/index.ts`, which look up a validator for the method and
 * refuse a result that does not match. Those two modules are the only
 * legitimate callers of this function, and `src/lib/ipc.bypass.test.ts` fails
 * the build if a third one appears.
 *
 * The name is deliberately unwelcoming. It was `rpc`, and eleven feature call
 * sites reached for it by habit and got an unchecked cast; `load_fasta` was
 * being called both ways at once, guarded from `sequenceSlice` and unguarded
 * from `BarcodeSetupPanel`.
 */
export async function rawSidecarRpc<T = unknown>(
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
