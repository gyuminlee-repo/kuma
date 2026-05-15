import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type {
  EvolveProSlice,
  EvolveProErrorKind,
  EvolveProProgress,
  EvolveProRunRequestParams,
} from "../slice-interfaces";
export type { EvolveProSlice };

import {
  detectEvolveProEnv,
  startEvolveProRun,
  cancelEvolveProRun,
} from "../../lib/ipc-kuro";

/**
 * EvolveProSlice (Wave 1b)
 *
 * Independent module. Does NOT call other slices' actions. UI continuity is
 * maintained via shared shadcn primitives only. Forward-compat: when later
 * integration into the main flow is desired, consumers of this slice can read
 * `evolveProResult.top_variants` and dispatch into `inputSlice.loadEvolveproCsv`
 * or `inputSlice.setMutationText` from the integration call site.
 */

function classifyError(message: string): EvolveProErrorKind {
  const m = message.toLowerCase();
  if (m.includes("env") && (m.includes("not found") || m.includes("missing"))) {
    return "env_not_found";
  }
  if (m.includes("network") || m.includes("connection") || m.includes("dns")) {
    return "network";
  }
  if (m.includes("disk") || m.includes("no space") || m.includes("enospc")) {
    return "disk_full";
  }
  if (m.includes("permission") || m.includes("eacces") || m.includes("denied")) {
    return "permission";
  }
  if (m.includes("runtime") || m.includes("subprocess") || m.includes("exit")) {
    return "runtime_error";
  }
  return "unknown";
}

export const createEvolveProSlice: StateCreator<
  AppState,
  [],
  [],
  EvolveProSlice
> = (set, get) => ({
  evolveProEnvStatus: null,
  evolveProRunId: null,
  evolveProProgress: null,
  evolveProResult: null,
  evolveProError: null,
  evolveProDetecting: false,
  evolveProRunning: false,

  detectEvolveProEnv: async () => {
    set({ evolveProDetecting: true, evolveProError: null });
    try {
      const status = await detectEvolveProEnv();
      set({ evolveProEnvStatus: status, evolveProDetecting: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({
        evolveProDetecting: false,
        evolveProError: { kind: classifyError(message), message },
      });
    }
  },

  startEvolveProRun: async (request: EvolveProRunRequestParams) => {
    set({
      evolveProRunning: true,
      evolveProError: null,
      evolveProResult: null,
      evolveProProgress: null,
      evolveProRunId: null,
    });
    try {
      const resp = await startEvolveProRun(request);
      set({ evolveProRunId: resp.run_id });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({
        evolveProRunning: false,
        evolveProError: { kind: classifyError(message), message },
      });
    }
  },

  cancelEvolveProRun: async () => {
    const runId = get().evolveProRunId;
    if (runId === null) return;
    try {
      await cancelEvolveProRun(runId);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ evolveProError: { kind: classifyError(message), message } });
    } finally {
      set({ evolveProRunning: false });
    }
  },

  setEvolveProProgress: (p: EvolveProProgress) => {
    set({ evolveProProgress: p });
    if (p.stage === "done") {
      set({ evolveProRunning: false });
    }
  },

  resetEvolveProState: () => {
    set({
      evolveProEnvStatus: null,
      evolveProRunId: null,
      evolveProProgress: null,
      evolveProResult: null,
      evolveProError: null,
      evolveProDetecting: false,
      evolveProRunning: false,
    });
  },
});
