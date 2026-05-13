/**
 * MAME Navigation slice: sub-step 상태 관리.
 *
 * currentMameSubStep은 현재 활성 sub-step ID를 나타낸다.
 * setMamePhase 호출 시 phaseSlice에서 해당 phase의 첫 sub-step으로 자동 리셋된다.
 *
 * goToNextStep: 현재 sub-step 다음으로 이동.
 *   - 현재 phase의 마지막 sub-step에서 호출 시 다음 phase의 첫 sub-step으로 이동하고
 *     setMamePhase를 자동 호출한다.
 * goToPrevStep: 이전 sub-step으로 이동. 첫 sub-step에서는 noop.
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type { MameSubStepId } from "./mameSubSteps";
import { MAME_SUBSTEP_ORDER } from "./mameSubSteps";
import type { MamePhase } from "./phaseSlice";

export type { MameSubStepId };
export { MAME_SUBSTEP_ORDER } from "./mameSubSteps";

const PHASE_ORDER: MamePhase[] = ["setup", "analyze", "activity"];

/** 전체 sub-step 목록 (phase 순서대로 평탄화) */
const ALL_SUBSTEPS: MameSubStepId[] = PHASE_ORDER.flatMap(
  (phase) => MAME_SUBSTEP_ORDER[phase],
);

function phaseOfSubStep(id: MameSubStepId): MamePhase {
  for (const phase of PHASE_ORDER) {
    if ((MAME_SUBSTEP_ORDER[phase] as readonly MameSubStepId[]).includes(id)) {
      return phase;
    }
  }
  return "setup";
}

export interface NavigationSlice {
  currentMameSubStep: MameSubStepId;
  setMameSubStep: (id: MameSubStepId) => void;
  goToNextStep: () => void;
  goToPrevStep: () => void;
}

export const createNavigationSlice: StateCreator<AppState, [], [], NavigationSlice> = (set, get) => ({
  currentMameSubStep: "setup.files",
  setMameSubStep: (id) => set({ currentMameSubStep: id }),
  goToNextStep: () => {
    const { currentMameSubStep, setMamePhase } = get();
    const idx = ALL_SUBSTEPS.indexOf(currentMameSubStep);
    if (idx < 0 || idx >= ALL_SUBSTEPS.length - 1) return;
    const nextStep = ALL_SUBSTEPS[idx + 1];
    const currentPhase = phaseOfSubStep(currentMameSubStep);
    const nextPhase = phaseOfSubStep(nextStep);
    if (nextPhase !== currentPhase) {
      // phase 경계 통과 — phaseSlice.setMamePhase가 sub-step도 리셋하므로 그쪽 사용
      setMamePhase(nextPhase);
    } else {
      set({ currentMameSubStep: nextStep });
    }
  },
  goToPrevStep: () => {
    const { currentMameSubStep, setMamePhase } = get();
    const idx = ALL_SUBSTEPS.indexOf(currentMameSubStep);
    if (idx <= 0) return;
    const prevStep = ALL_SUBSTEPS[idx - 1];
    const currentPhase = phaseOfSubStep(currentMameSubStep);
    const prevPhase = phaseOfSubStep(prevStep);
    if (prevPhase !== currentPhase) {
      setMamePhase(prevPhase);
      // phase가 바뀌면 phaseSlice가 첫 sub-step으로 리셋하므로, 원하는 prevStep으로 다시 세팅
      set({ currentMameSubStep: prevStep });
    } else {
      set({ currentMameSubStep: prevStep });
    }
  },
});
