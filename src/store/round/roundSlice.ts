/**
 * roundSlice.ts — Round 엔티티 Zustand slice
 *
 * Round는 KURO·MAME 상태를 wrap하는 상위 레이어.
 * Task 5.1에서 handoffNextRound가 보강 예정. Phase 3에서는 stub.
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.1, §2.3
 */

import { create } from "zustand"
import type { Round, RoundStatus, RoundErrorInfo } from "@/types/round"
import type { PlateMeta } from "@/types/mame/activity"

export interface RoundSliceState {
  rounds: Round[]
  active_round_id: string | null
}

export interface RoundSliceActions {
  /** 새 라운드 생성. 생성된 round_id 반환. active_round_id를 신규 id로 설정. */
  addRound: (init: { plate_meta: PlateMeta }) => string
  /** 라운드 status 전이. error 상태 시 error_info 선택적 설정. */
  transitionStatus: (
    round_id: string,
    status: RoundStatus,
    error_info?: RoundErrorInfo
  ) => void
  /** 활성 라운드 변경 */
  setActiveRound: (round_id: string) => void
  /** 특정 라운드의 단일 필드 업데이트 */
  updateRoundField: <K extends keyof Round>(
    round_id: string,
    field: K,
    value: Round[K]
  ) => void
  /**
   * 다음 라운드 핸드오프. Task 5.1에서 보강 예정.
   * Phase 3: stub — null 반환.
   */
  handoffNextRound: (prevRoundId: string) => null
}

export type RoundSlice = RoundSliceState & RoundSliceActions

export const createRoundStore = () =>
  create<RoundSlice>()((set, get) => ({
    rounds: [],
    active_round_id: null,

    addRound: (init) => {
      const existing = get().rounds
      const n = existing.length + 1
      const id = `round_${n}`
      const round: Round = {
        id,
        n,
        created_at: new Date().toISOString(),
        status: "design",
        error_info: null,
        plate_meta: init.plate_meta,
        design: {},
        genotype: {},
        activity: null,
        merged_table: [],
      }
      set((state) => ({
        rounds: [...state.rounds, round],
        active_round_id: id,
      }))
      return id
    },

    transitionStatus: (round_id, status, error_info) => {
      set((state) => ({
        rounds: state.rounds.map((r) =>
          r.id === round_id
            ? {
                ...r,
                status,
                error_info: error_info !== undefined ? error_info : r.error_info,
              }
            : r
        ),
      }))
    },

    setActiveRound: (round_id) => {
      set({ active_round_id: round_id })
    },

    updateRoundField: (round_id, field, value) => {
      set((state) => ({
        rounds: state.rounds.map((r) =>
          r.id === round_id ? { ...r, [field]: value } : r
        ),
      }))
    },

    handoffNextRound: (_prevRoundId) => {
      // Phase 3 stub — Task 5.1에서 보강 예정
      return null
    },
  }))

/**
 * 앱 전역 싱글턴 Round store.
 * MAME 활성 데이터 흐름의 최상위 레이어.
 */
export const useRoundStore = createRoundStore()
