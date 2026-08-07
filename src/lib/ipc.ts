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

// === MAME strategy advisory RPC (Fork D) =====================================

/**
 * Advisory classify() call with per-round xlsx file references.
 *
 * @param roundFiles - Ordered list of {n, path, wt_values?} xlsx file entries.
 *   n is 1-based round number; handler sorts by n internally. wt_values are the
 *   wild-type replicates step 4.1 recorded for that round, which the file
 *   itself cannot carry; only the highest-numbered entry is read.
 * @param cNext - Optional capacity of the next combinatorial plate (wells).
 *   Used to derive K_throughput = floor((1+sqrt(1+8*cNext))/2). Defaults to 96.
 * @returns ClassifyDecisionResult when the classifier answered, or
 *   ClassifyNotAssessableResult when the bootstrap gate was reached with too
 *   few wild-type replicates to run on, so the question could not be put to it.
 *   Discriminate on `advisory`.
 *   Throws a JSON-RPC error (-32602 / -32002) on bad input or missing/malformed files.
 *
 * Read-only, no confirmation button, no PI decision persistence.
 * MAME sidecar strategy.classify_round 호출.
 */
export async function classifyRound(
  roundFiles: import("@/types/mame/strategy").RoundFileEntry[],
  cNext?: number,
): Promise<import("@/types/mame/strategy").ClassifyRoundResult> {
  return rpc("mame", "strategy.classify_round", {
    round_files: roundFiles,
    ...(cNext !== undefined && { c_next: cNext }),
  });
}
