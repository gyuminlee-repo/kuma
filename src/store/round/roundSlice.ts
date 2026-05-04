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

/** loadRoundActivity 콜백 타입. KURO inputSlice.loadRoundActivity와 동일 시그니처. */
export type LoadRoundActivityFn = (prevRound: Round) => { ok: boolean; warnings: string[] }

export interface HandoffOptions {
  /**
   * KURO inputSlice.loadRoundActivity를 주입.
   * roundSlice는 KURO store에 직접 의존하지 않으므로 콜백으로 분리 (의존 그래프 명시화).
   */
  loadRoundActivity: LoadRoundActivityFn
  /** 핸드오프 성공 시 호출 (예: KURO 탭 전환). 탭 store 없으면 UI 레이어에서 주입. */
  onHandoffSuccess?: () => void
}

export interface HandoffResult {
  ok: boolean
  warnings: string[]
  newRoundId: string | null
}

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
   * 다음 라운드 핸드오프 (1-click flow).
   * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.3
   *
   * 흐름:
   * 1. prevRound.status = "exported"
   * 2. 새 Round 생성 (n+1, status="design", plate_meta 상속)
   * 3. loadRoundActivity(prevRound) 호출
   * 4. 실패 시 새 round 롤백 + prevRound status 원복
   * 5. 성공 시 setActiveRound(newRoundId) + onHandoffSuccess 콜백
   *
   * KURO inputSlice와의 결합을 피하기 위해 loadRoundActivity를 콜백으로 주입.
   * UI 레이어(RoundHandoffButton)에서 useAppStore().loadRoundActivity를 전달할 것.
   */
  handoffNextRound: (prevRoundId: string, opts: HandoffOptions) => HandoffResult
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

    handoffNextRound: (prevRoundId, opts) => {
      const { loadRoundActivity, onHandoffSuccess } = opts
      const state = get()

      // Fail-safe: prevRound 존재 확인
      const prevRound = state.rounds.find((r) => r.id === prevRoundId)
      if (!prevRound) {
        return {
          ok: false,
          warnings: [`prevRound not found: ${prevRoundId}`],
          newRoundId: null,
        }
      }

      const prevStatus = prevRound.status

      // Step 1: prevRound.status = "exported"
      set((s) => ({
        rounds: s.rounds.map((r) =>
          r.id === prevRoundId ? { ...r, status: "exported" as const } : r
        ),
      }))

      // Step 2: 새 Round 생성 (n+1, status="design", plate_meta 상속)
      const existing = get().rounds
      const n = existing.length + 1
      const newRoundId = `round_${n}`
      const newRound: Round = {
        id: newRoundId,
        n,
        created_at: new Date().toISOString(),
        status: "design",
        error_info: null,
        plate_meta: prevRound.plate_meta,
        design: {},
        genotype: {},
        activity: null,
        merged_table: [],
      }
      set((s) => ({
        rounds: [...s.rounds, newRound],
        active_round_id: newRoundId,
      }))

      // Step 3: KURO inputSlice.loadRoundActivity 호출
      const hydrateResult = loadRoundActivity(prevRound)

      // Step 4: 실패 시 롤백
      if (!hydrateResult.ok) {
        set((s) => ({
          // 새 round 제거
          rounds: s.rounds
            .filter((r) => r.id !== newRoundId)
            .map((r) =>
              r.id === prevRoundId ? { ...r, status: prevStatus } : r
            ),
          active_round_id: prevRoundId,
        }))
        return {
          ok: false,
          warnings: hydrateResult.warnings,
          newRoundId: null,
        }
      }

      // Step 5: 성공
      if (onHandoffSuccess) {
        onHandoffSuccess()
      }

      return {
        ok: true,
        warnings: [],
        newRoundId,
      }
    },
  }))

/**
 * 앱 전역 싱글턴 Round store.
 * MAME 활성 데이터 흐름의 최상위 레이어.
 */
export const useRoundStore = createRoundStore()
