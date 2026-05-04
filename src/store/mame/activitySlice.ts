/**
 * activitySlice.ts — MAME 활성 데이터 RPC wrapper store
 *
 * 백엔드 activity.* RPC 4개를 wrapping하여 Round 상태를 갱신.
 * RoundStore를 주입받아 round 상태를 직접 업데이트.
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4
 */

import { create } from "zustand"
import { sendRequest } from "@/lib/ipc-mame"
import { formatError } from "@/lib/utils"
import type {
  ActivityRecord,
  MergeStats,
  MergedRow,
  PlateMeta,
} from "@/types/mame/activity"
import type { RoundSlice } from "@/store/round/roundSlice"

// ─── RPC response shapes ─────────────────────────────────────────────────────

interface ActivityUploadResponse {
  records: ActivityRecord[]
  plate_meta: PlateMeta
}

interface ActivityMergeResponse {
  merged: MergedRow[]
  stats: MergeStats
}

// ─── Round store reference type (minimal interface for DI) ────────────────────

type RoundStoreRef = {
  getState: () => Pick<RoundSlice, "rounds" | "active_round_id" | "updateRoundField" | "transitionStatus">
}

// ─── Slice interface ─────────────────────────────────────────────────────────

export interface ActivitySliceState {
  isUploading: boolean
  isExporting: boolean
  isMerging: boolean
  uploadError: string | null
  mergeError: string | null
  exportError: string | null
  lastMergeStats: MergeStats | null
}

export interface ActivitySliceActions {
  /**
   * 활성 데이터 파일 업로드.
   * activity.upload RPC → round.activity.raw_records 갱신 (updateRoundField via roundStore).
   */
  uploadActivityFile: (
    round_id: string,
    file_path: string,
    format: "long_csv" | "long_xlsx"
  ) => Promise<void>
  /**
   * WT 웰 / 컨트롤 웰 메타 설정.
   * activity.set_plate_meta RPC 호출.
   */
  setPlateMeta: (round_id: string, plate_meta: PlateMeta) => Promise<void>
  /**
   * KURO 디자인 + 활성 데이터 병합.
   * activity.merge RPC → round.merged_table 갱신 + status="activity_linked".
   * 실패 시 round.error_info 채움 + status="error".
   */
  mergeActivity: (round_id: string) => Promise<void>
  /**
   * EVOLVEpro CSV 내보내기.
   * activity.export_evolvepro_csv RPC 호출.
   */
  exportEvolveproCsv: (round_id: string, path: string) => Promise<void>
}

export type ActivitySlice = ActivitySliceState & ActivitySliceActions

const RPC_TIMEOUT_MS = 60_000

// ─── Factory (DI 패턴: roundStore 주입) ─────────────────────────────────────

export function createActivityStore(roundStore: RoundStoreRef) {
  return create<ActivitySlice>()((set) => ({
    isUploading: false,
    isExporting: false,
    isMerging: false,
    uploadError: null,
    mergeError: null,
    exportError: null,
    lastMergeStats: null,

    uploadActivityFile: async (round_id, file_path, format) => {
      set({ isUploading: true, uploadError: null })
      try {
        const result = await sendRequest<ActivityUploadResponse>(
          "activity.upload",
          { round_id, file_path, format },
          RPC_TIMEOUT_MS
        )
        roundStore.getState().updateRoundField(round_id as never, "activity" as never, {
          records: result.records,
          plate_meta: result.plate_meta,
        } as never)
      } catch (err) {
        set({ uploadError: formatError(err) })
      } finally {
        set({ isUploading: false })
      }
    },

    setPlateMeta: async (round_id, plate_meta) => {
      try {
        await sendRequest(
          "activity.set_plate_meta",
          { round_id, plate_meta },
          RPC_TIMEOUT_MS
        )
      } catch (err) {
        set({ uploadError: formatError(err) })
      }
    },

    mergeActivity: async (round_id) => {
      set({ isMerging: true, mergeError: null })
      try {
        const result = await sendRequest<ActivityMergeResponse>(
          "activity.merge",
          { round_id },
          RPC_TIMEOUT_MS
        )
        roundStore.getState().updateRoundField(round_id as never, "merged_table" as never, result.merged as never)
        roundStore.getState().transitionStatus(round_id, "activity_linked")
        set({ lastMergeStats: result.stats })
      } catch (err) {
        const message = formatError(err)
        set({ mergeError: message })
        roundStore.getState().transitionStatus(round_id, "error", {
          stage: "merge",
          message,
          occurred_at: new Date().toISOString(),
        })
      } finally {
        set({ isMerging: false })
      }
    },

    exportEvolveproCsv: async (round_id, path) => {
      set({ isExporting: true, exportError: null })
      try {
        await sendRequest(
          "activity.export_evolvepro_csv",
          { round_id, path },
          RPC_TIMEOUT_MS
        )
      } catch (err) {
        set({ exportError: formatError(err) })
      } finally {
        set({ isExporting: false })
      }
    },
  }))
}

/**
 * 앱 전역 싱글턴 Activity store.
 * roundStore와 함께 초기화되어야 하므로 lazy init 패턴 사용.
 * initActivityStore() 호출 후 useActivityStore 사용 가능.
 */
let _store: ReturnType<typeof createActivityStore> | null = null

export function initActivityStore(roundStore: RoundStoreRef): void {
  _store = createActivityStore(roundStore)
}

export function useActivityStore(): ReturnType<typeof createActivityStore> {
  if (!_store) {
    throw new Error(
      "useActivityStore: initActivityStore()를 먼저 호출하세요."
    )
  }
  return _store
}
