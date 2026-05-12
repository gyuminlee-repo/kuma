/**
 * MAME Navigation slice: sub-step 상태 관리.
 *
 * currentMameSubStep은 현재 활성 sub-step ID를 나타낸다.
 * setMamePhase 호출 시 phaseSlice에서 해당 phase의 첫 sub-step으로 자동 리셋된다.
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type { MameSubStepId } from "./mameSubSteps";

export type { MameSubStepId };
export { MAME_SUBSTEP_ORDER } from "./mameSubSteps";

export interface NavigationSlice {
  currentMameSubStep: MameSubStepId;
  setMameSubStep: (id: MameSubStepId) => void;
}

export const createNavigationSlice: StateCreator<AppState, [], [], NavigationSlice> = (set) => ({
  currentMameSubStep: "setup.files",
  setMameSubStep: (id) => set({ currentMameSubStep: id }),
});
