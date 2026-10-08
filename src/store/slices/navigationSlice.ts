import type { StateCreator } from "zustand";
import type { AppState } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MajorStepId = "design" | "output" | "export";
export type SubStepId =
  | "design.load"
  | "design.mutation"
  | "design.params"
  | "design.submit"
  | "output.summary"
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
  goToNextStep: () => void;
  goToPrevStep: () => void;
  canGoNext: () => boolean;
  canGoPrev: () => boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const MAJOR_ORDER: MajorStepId[] = ["design", "output", "export"];

export const SUBSTEP_ORDER: Record<MajorStepId, SubStepId[]> = {
  design: [
    "design.load",
    "design.mutation",
    "design.params",
    "design.submit",
  ],
  output: ["output.summary"],
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
> = (set, get) => ({
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

  goToNextStep() {
    const { currentMajor, currentSubStep } = get();
    const subSteps = SUBSTEP_ORDER[currentMajor];
    const idx = subSteps.indexOf(currentSubStep);
    if (idx < subSteps.length - 1) {
      set({ currentSubStep: subSteps[idx + 1] });
    } else {
      const majorIdx = MAJOR_ORDER.indexOf(currentMajor);
      if (majorIdx < MAJOR_ORDER.length - 1) {
        const nextMajor = MAJOR_ORDER[majorIdx + 1];
        set({ currentMajor: nextMajor, currentSubStep: SUBSTEP_ORDER[nextMajor][0] });
      }
      // 마지막 step이면 noop
    }
  },

  goToPrevStep() {
    const { currentMajor, currentSubStep } = get();
    const subSteps = SUBSTEP_ORDER[currentMajor];
    const idx = subSteps.indexOf(currentSubStep);
    if (idx > 0) {
      set({ currentSubStep: subSteps[idx - 1] });
    } else {
      const majorIdx = MAJOR_ORDER.indexOf(currentMajor);
      if (majorIdx > 0) {
        const prevMajor = MAJOR_ORDER[majorIdx - 1];
        const prevSubSteps = SUBSTEP_ORDER[prevMajor];
        set({
          currentMajor: prevMajor,
          currentSubStep: prevSubSteps[prevSubSteps.length - 1],
        });
      }
      // 첫 step이면 noop
    }
  },

  canGoNext() {
    const { currentMajor, currentSubStep } = get();
    const isLastMajor = currentMajor === MAJOR_ORDER[MAJOR_ORDER.length - 1];
    if (isLastMajor) {
      const subSteps = SUBSTEP_ORDER[currentMajor];
      return currentSubStep !== subSteps[subSteps.length - 1];
    }
    return true;
  },

  canGoPrev() {
    const { currentMajor, currentSubStep } = get();
    const isFirstMajor = currentMajor === MAJOR_ORDER[0];
    if (isFirstMajor) {
      return currentSubStep !== SUBSTEP_ORDER[currentMajor][0];
    }
    return true;
  },
});
