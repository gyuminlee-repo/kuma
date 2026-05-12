import type { StateCreator } from "zustand";
import type { AppState } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MajorStepId = "variant" | "sdm" | "plate" | "export";
export type SubStepId = string; // e.g. "variant.load"

export interface StepStatus {
  done: boolean;
  reachable: boolean; // always true in v1 (free navigation); gating reserved for v2
}

export interface NavigationSlice {
  // State
  currentMajor: MajorStepId;
  currentSubStep: SubStepId;
  stepStatus: Record<SubStepId, StepStatus>;

  // Actions
  setMajor: (id: MajorStepId) => void;
  setSubStep: (id: SubStepId) => void;
  markDone: (id: SubStepId) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const MAJOR_ORDER: MajorStepId[] = ["variant", "sdm", "plate", "export"];

export const SUBSTEP_ORDER: Record<MajorStepId, SubStepId[]> = {
  variant: [
    "variant.load",
    "variant.select",
    "variant.adaptive",
    "variant.domain",
    "variant.pareto",
  ],
  sdm: [
    "sdm.mutations",
    "sdm.codon",
    "sdm.polymerase",
    "sdm.gc",
    "sdm.run",
  ],
  plate: ["plate.size", "plate.layout", "plate.labels"],
  export: ["export.format", "export.summary", "export.workspace"],
};

// ---------------------------------------------------------------------------
// Initial state helper
// ---------------------------------------------------------------------------

function buildInitialStepStatus(): Record<SubStepId, StepStatus> {
  const status: Record<SubStepId, StepStatus> = {};
  for (const steps of Object.values(SUBSTEP_ORDER)) {
    for (const id of steps) {
      status[id] = { done: false, reachable: true };
    }
  }
  return status;
}

// ---------------------------------------------------------------------------
// Slice factory
// ---------------------------------------------------------------------------

export const createNavigationSlice: StateCreator<
  AppState,
  [],
  [],
  NavigationSlice
> = (set) => ({
  currentMajor: "variant",
  currentSubStep: "variant.load",
  stepStatus: buildInitialStepStatus(),

  setMajor(id: MajorStepId) {
    const firstSubStep = SUBSTEP_ORDER[id][0];
    set({ currentMajor: id, currentSubStep: firstSubStep });
  },

  setSubStep(id: SubStepId) {
    // prefix 매칭으로 major 자동 추론
    const inferredMajor = MAJOR_ORDER.find((m) =>
      id.startsWith(m + "."),
    ) as MajorStepId | undefined;

    if (!inferredMajor) return; // ignore unknown sub-step ID

    set({ currentMajor: inferredMajor, currentSubStep: id });
  },

  markDone(id: SubStepId) {
    set((state) => ({
      stepStatus: {
        ...state.stepStatus,
        [id]: { ...state.stepStatus[id], done: true },
      },
    }));
  },
});
