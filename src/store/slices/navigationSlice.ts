import type { StateCreator } from "zustand";
import type { AppState } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MajorStepId = "design" | "plate" | "export";
export type SubStepId =
  | "design.load"
  | "design.variant"
  | "design.mutation"
  | "design.params"
  | "plate.layout"
  | "export.all";

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

export const MAJOR_ORDER: MajorStepId[] = ["design", "plate", "export"];

export const SUBSTEP_ORDER: Record<MajorStepId, SubStepId[]> = {
  design: [
    "design.load",
    "design.variant",
    "design.mutation",
    "design.params",
  ],
  plate: ["plate.layout"],
  export: ["export.all"],
};

// ---------------------------------------------------------------------------
// Initial state helper
// ---------------------------------------------------------------------------

function buildInitialStepStatus(): Record<SubStepId, StepStatus> {
  const status: Record<SubStepId, StepStatus> = {} as Record<SubStepId, StepStatus>;
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
  currentMajor: "design",
  currentSubStep: "design.load",
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
