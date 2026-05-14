/**
 * MAME Phase slice: 1. Barcode Setup / 2. Analyze 탭 전환 상태.
 *
 * Phase는 localStorage key `kuma:mame:phase`에 영속화된다.
 * 초기값: localStorage에 저장된 값이 있으면 사용, 없으면 "analyze" (기존 동작 보존).
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import { MAME_SUBSTEP_ORDER } from "./mameSubSteps";

const PHASE_STORAGE_KEY = "kuma:mame:phase";

export type MamePhase = "setup" | "analyze" | "activity";
export type ActivityTab = "ingest" | "merge" | "export";
const ACTIVITY_TAB_STORAGE_KEY = "kuma:mame:activityTab";

function readActivityTabFromStorage(): ActivityTab {
  try {
    const stored = localStorage.getItem(ACTIVITY_TAB_STORAGE_KEY);
    if (stored === "ingest" || stored === "merge" || stored === "export") return stored;
  } catch {
    // localStorage 접근 실패 시 기본값
  }
  return "ingest";
}

export interface PhaseSlice {
  mamePhase: MamePhase;
  setMamePhase: (phase: MamePhase) => void;
  activityTab: ActivityTab;
  setActivityTab: (tab: ActivityTab) => void;
  resetPhase: () => void;
}

const PHASE_INITIAL: MamePhase = "analyze";
const ACTIVITY_TAB_INITIAL: ActivityTab = "ingest";

function readPhaseFromStorage(): MamePhase {
  try {
    const stored = localStorage.getItem(PHASE_STORAGE_KEY);
    if (stored === "setup" || stored === "analyze" || stored === "activity") return stored;
  } catch {
    // localStorage 접근 실패 시 기본값 사용
  }
  return "analyze";
}

export const createPhaseSlice: StateCreator<AppState, [], [], PhaseSlice> = (set) => ({
  mamePhase: readPhaseFromStorage(),
  setMamePhase: (phase) => {
    try {
      localStorage.setItem(PHASE_STORAGE_KEY, phase);
    } catch {
      // 저장 실패 시 상태만 업데이트
    }
    set({
      mamePhase: phase,
      currentMameSubStep: MAME_SUBSTEP_ORDER[phase][0],
    });
  },
  activityTab: readActivityTabFromStorage(),
  setActivityTab: (tab) => {
    try {
      localStorage.setItem(ACTIVITY_TAB_STORAGE_KEY, tab);
    } catch {
      // 저장 실패 시 상태만 업데이트
    }
    set({ activityTab: tab });
  },
  resetPhase: () => {
    try {
      localStorage.removeItem(PHASE_STORAGE_KEY);
      localStorage.removeItem(ACTIVITY_TAB_STORAGE_KEY);
    } catch {
      // localStorage 접근 실패 시 in-memory만 초기화
    }
    set({
      mamePhase: PHASE_INITIAL,
      activityTab: ACTIVITY_TAB_INITIAL,
      currentMameSubStep: MAME_SUBSTEP_ORDER[PHASE_INITIAL][0],
    });
  },
});
