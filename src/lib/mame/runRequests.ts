import { sendRequest } from "@/lib/ipc-mame";
import type { AppState } from "@/store/mame/types";

export type MameRunScope = "primary" | "resequence";

const stores = new Map<MameRunScope, () => AppState>();
const cacheConsumers = new Set([
  "get_plate_data", "get_run_health", "export_excel", "export_run_report",
  "apply_selection_overrides", "export_janus_mapping", "export_janus_mapping_dry_run",
]);

export function registerRunStore(scope: MameRunScope, get: () => AppState): void {
  stores.set(scope, get);
}

export function otherRunBusy(scope: MameRunScope = "primary"): boolean {
  return [...stores].some(([key, get]) => key !== scope && get().isAnalyzing);
}

export function sendRunRequest<T>(
  state: AppState,
  method: string,
  params: Record<string, unknown> = {},
  timeoutMs?: number,
): Promise<T> {
  const scoped = {
    ...params,
    ...(state.runScope === "resequence" ? { run_scope: "resequence" } : {}),
    ...(state.analyzeResult && cacheConsumers.has(method)
      ? { result_snapshot: state.analyzeResult } : {}),
  };
  return timeoutMs === undefined
    ? sendRequest<T>(method, scoped)
    : sendRequest<T>(method, scoped, timeoutMs);
}

/** Cancellation restarts the process, not the independent completed runs. */
export async function restoreRunCaches(): Promise<void> {
  for (const [scope, get] of stores) {
    const result = get().analyzeResult;
    if (result) {
      await sendRequest("load_analyze_result", { ...result, run_scope: scope });
    }
  }
}
