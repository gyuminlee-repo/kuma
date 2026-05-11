/**
 * MAME Phase slice: 1. Barcode Setup / 2. Analyze 탭 전환 상태.
 *
 * Phase는 localStorage key `kuma:mame:phase`에 영속화된다.
 * 초기값: localStorage에 저장된 값이 있으면 사용, 없으면 "analyze" (기존 동작 보존).
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";

const PHASE_STORAGE_KEY = "kuma:mame:phase";

export type MamePhase = "setup" | "analyze";

export interface PhaseSlice {
  mamePhase: MamePhase;
  setMamePhase: (phase: MamePhase) => void;
}

function readPhaseFromStorage(): MamePhase {
  try {
    const stored = localStorage.getItem(PHASE_STORAGE_KEY);
    if (stored === "setup" || stored === "analyze") return stored;
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
    set({ mamePhase: phase });
  },
});
