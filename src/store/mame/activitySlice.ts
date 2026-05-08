/**
 * activitySlice.ts — MAME 활성 데이터 RPC wrapper store
 *
 * 백엔드 activity.* RPC 4개를 wrapping하여 Round 상태를 갱신.
 * RoundStore를 주입받아 round 상태를 직접 업데이트.
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4
 */

import { create } from "zustand"
import { readTextFile } from "@tauri-apps/plugin-fs"
import { notifyJobComplete } from "@/lib/notify"
import { notifyJobDone, notifyJobError } from "@/lib/toast"
import { startKeepAwake, stopKeepAwake } from "@/lib/keepAwake"
import { sendRequest } from "@/lib/ipc-mame"
import { formatError } from "@/lib/utils"
import {
  validateCsvHeader,
  extractCsvHeader,
  MAME_ACTIVITY_CSV_SCHEMA,
} from "@/lib/schemaValidator"
import type {
  ActivityRecord,
  MergeForEvolveproResponse,
  MergeReplicatesStats,
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
  /**
   * Phase B: replicate merge 통계.
   * merge_for_evolvepro RPC wire-up 후 채워짐.
   * 현재는 null 초기화만 (placeholder for v0.3 Phase C wire-up).
   */
  lastReplicateStats: MergeReplicatesStats | null
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
  /**
   * v0.3 신규: 라벨 교체 가드 + replicate 병합 통합 병합.
   * mame.activity.merge_for_evolvepro RPC → round.merged_table 갱신 + status="activity_linked".
   * 기존 mergeActivity와 별도 분기. 5/12 demo path를 건드리지 않음.
   */
  mergeForEvolvepro: (
    round_id: string,
    options?: {
      prev_round_evolvepro?: Record<string, number>
      authoritative_measurements?: Record<string, number[]>
      fallback_measurements?: Record<string, number[]>
      mismatch_threshold?: number
      ref_seq?: string
    }
  ) => Promise<void>
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
    lastReplicateStats: null,

    uploadActivityFile: async (round_id, file_path, format) => {
      set({ isUploading: true, uploadError: null })

      // §3 Input Guards: CSV 형식일 때만 sidecar 호출 전 헤더 검증
      // xlsx 는 바이너리이므로 frontend 검증 불가 — sidecar 에 위임
      if (format === "long_csv") {
        try {
          const csvText = await readTextFile(file_path)
          const header = extractCsvHeader(csvText)
          const validation = validateCsvHeader(header, MAME_ACTIVITY_CSV_SCHEMA)
          if (!validation.valid) {
            const detail = validation.errors.join("; ")
            set({
              uploadError: `CSV 형식 오류: ${detail}`,
              isUploading: false,
            })
            return
          }
        } catch {
          // 파일 읽기 실패 시 sidecar 에 위임
        }
      }

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
      const _mergeStartedAt = Date.now()
      set({ isMerging: true, mergeError: null })
      void startKeepAwake("KUMA activity merge")
      try {
        const result = await sendRequest<ActivityMergeResponse>(
          "activity.merge",
          { round_id },
          RPC_TIMEOUT_MS
        )
        roundStore.getState().updateRoundField(round_id as never, "merged_table" as never, result.merged as never)
        roundStore.getState().transitionStatus(round_id, "activity_linked")
        // legacy 응답에는 replicate_stats 없으므로 명시 null 세팅
        set({ lastMergeStats: result.stats, lastReplicateStats: null })
        // §13: notify if merge took long enough
        void notifyJobComplete({ title: "Activity merge complete", body: "Merged activity data ready", startedAt: _mergeStartedAt })
        // §8: In-app toast (always fires)
        notifyJobDone({ title: "Activity merge complete", description: "Merged activity data ready", durationMs: Date.now() - _mergeStartedAt })
      } catch (err) {
        const message = formatError(err)
        set({ mergeError: message })
        roundStore.getState().transitionStatus(round_id, "error", {
          stage: "merge",
          message,
          occurred_at: new Date().toISOString(),
        })
        notifyJobError("Activity merge failed", err)
      } finally {
        void stopKeepAwake()
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

    mergeForEvolvepro: async (round_id, options) => {
      const _mergeForEvolveproStartedAt = Date.now()
      set({ isMerging: true, mergeError: null })
      void startKeepAwake("KUMA EVOLVEpro merge")
      try {
        const params: {
          round_id: string
          prev_round_evolvepro: Record<string, number>
          authoritative_measurements?: Record<string, number[]>
          fallback_measurements?: Record<string, number[]>
          mismatch_threshold?: number
          ref_seq?: string
        } = {
          round_id,
          // prev_round_evolvepro는 백엔드에서 required — 미전달 시 빈 맵으로 기본 세팅 (Round 1 동작)
          prev_round_evolvepro: options?.prev_round_evolvepro ?? {},
        }
        if (options?.authoritative_measurements !== undefined) {
          params.authoritative_measurements = options.authoritative_measurements
        }
        if (options?.fallback_measurements !== undefined) {
          params.fallback_measurements = options.fallback_measurements
        }
        if (options?.mismatch_threshold !== undefined) {
          params.mismatch_threshold = options.mismatch_threshold
        }
        if (options?.ref_seq !== undefined) {
          params.ref_seq = options.ref_seq
        }

        const res = await sendRequest<MergeForEvolveproResponse>(
          "mame.activity.merge_for_evolvepro",
          params,
          RPC_TIMEOUT_MS
        )
        roundStore.getState().updateRoundField(round_id as never, "merged_table" as never, res.merged as never)
        roundStore.getState().transitionStatus(round_id, "activity_linked")
        set({
          lastMergeStats: res.stats,
          lastReplicateStats: res.replicate_stats,
        })
        // §13: notify if merge took long enough
        void notifyJobComplete({ title: "Merge complete", body: "EVOLVEpro merge ready", startedAt: _mergeForEvolveproStartedAt })
        // §8: In-app toast (always fires)
        notifyJobDone({ title: "Merge complete", description: "EVOLVEpro merge ready", durationMs: Date.now() - _mergeForEvolveproStartedAt })
      } catch (err) {
        const message = formatError(err)
        set({ mergeError: message })
        roundStore.getState().transitionStatus(round_id, "error", {
          stage: "merge",
          message,
          occurred_at: new Date().toISOString(),
        })
        notifyJobError("EVOLVEpro merge failed", err)
      } finally {
        void stopKeepAwake()
        set({ isMerging: false })
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

/**
 * 비-React 컨텍스트(onCloseRequested 등)에서 상태를 읽을 때 사용.
 * store가 초기화되지 않은 경우 null을 반환하므로 null 체크 필수.
 */
export function getActivityStore(): ReturnType<typeof createActivityStore> | null {
  return _store
}
