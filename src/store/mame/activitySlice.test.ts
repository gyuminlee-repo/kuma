/**
 * activitySlice.test.ts — Task 3.2 단위 테스트
 * TDD: 실패 테스트 먼저 작성
 *
 * ipc-mame sendRequest를 mock하여 순수 store 동작만 검증.
 */

import { describe, it, expect, vi, beforeEach } from "vitest"
import type { ActivityRecord, MergedRow, MergeReplicatesStats, MergeStats, PlateMeta } from "@/types/mame/activity"

// ─── RPC mock ───────────────────────────────────────────────────────────────
const mockSendRequest = vi.fn()
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
}))

// ─── import after mock ───────────────────────────────────────────────────────
import { createActivityStore } from "./activitySlice"

const mockRecords: ActivityRecord[] = [
  {
    plate_id: "P01",
    well_id: "A01",
    value: 1.23,
    replicate_idx: 1,
    is_wt: true,
    source_file: "round1.csv",
  },
]

const mockMergedRows: MergedRow[] = [
  {
    plate_id: "P01",
    well_id: "B03",
    mutation: "F89W",
    mutation_source: "kuro_design",
    expected_mutation: "F89W",
    called_mutation: "F89W",
    ngs_success: true,
    activity_raw_mean: 2.45,
    activity_raw_sd: 0.12,
    activity_replicates: [2.40, 2.50, 2.45],
    replicate_n: 3,
    fold_change: 1.99,
    log2_fc: 0.99,
  },
]

const mockMergeStats: MergeStats = {
  n_total_wells: 96,
  n_with_activity: 96,
  n_with_genotype: 90,
  n_ngs_success: 88,
  n_wt: 4,
  n_duplicate_warnings: 0,
  n_excluded_from_export: 10,
}

const mockReplicateStats: MergeReplicatesStats = {
  authoritative_count: 5,
  fallback_count: 3,
  merged_count: 8,
  mismatched: [],
}

// getState를 매번 동일 객체 반환하도록 고정
const mockStateActions = {
  rounds: [
    {
      id: "round_1",
      n: 1,
      status: "design" as const,
      error_info: null,
      plate_meta: { plates: [] },
      design: {},
      genotype: {},
      activity: null,
      merged_table: [],
      created_at: new Date().toISOString(),
    },
  ],
  active_round_id: "round_1",
  updateRoundField: vi.fn(),
  transitionStatus: vi.fn(),
}

const mockRoundStore = {
  getState: () => mockStateActions,
}

describe("activitySlice", () => {
  let store: ReturnType<typeof createActivityStore>

  beforeEach(() => {
    vi.clearAllMocks()
    // mock 함수 초기화 (vi.clearAllMocks가 impl까지 지우므로 재등록)
    mockStateActions.updateRoundField = vi.fn()
    mockStateActions.transitionStatus = vi.fn()
    store = createActivityStore(mockRoundStore as Parameters<typeof createActivityStore>[0])
  })

  describe("uploadActivityFile", () => {
    it("calls activity.upload RPC with correct params", async () => {
      const mockPlate: PlateMeta = { plates: [] }
      mockSendRequest.mockResolvedValueOnce({
        records: mockRecords,
        plate_meta: mockPlate,
      })
      await store.getState().uploadActivityFile("round_1", "/path/to/round1.csv", "long_csv")
      expect(mockSendRequest).toHaveBeenCalledWith(
        "activity.upload",
        { round_id: "round_1", file_path: "/path/to/round1.csv", format: "long_csv" },
        expect.any(Number)
      )
    })

    it("sets isUploading false after success", async () => {
      mockSendRequest.mockResolvedValueOnce({ records: mockRecords, plate_meta: { plates: [] } })
      await store.getState().uploadActivityFile("round_1", "/path/to/file.csv", "long_csv")
      expect(store.getState().isUploading).toBe(false)
    })

    it("sets uploadError on RPC failure", async () => {
      mockSendRequest.mockRejectedValueOnce(new Error("CSV parse error"))
      await store.getState().uploadActivityFile("round_1", "/bad.csv", "long_csv")
      expect(store.getState().uploadError).toContain("CSV parse error")
      expect(store.getState().isUploading).toBe(false)
    })
  })

  describe("setPlateMeta", () => {
    it("calls activity.set_plate_meta RPC", async () => {
      mockSendRequest.mockResolvedValueOnce({})
      const meta: PlateMeta = { plates: [{ plate_id: "P01", wt_wells: ["A01"], control_wells: [] }] }
      await store.getState().setPlateMeta("round_1", meta)
      expect(mockSendRequest).toHaveBeenCalledWith(
        "activity.set_plate_meta",
        { round_id: "round_1", plate_meta: meta },
        expect.any(Number)
      )
    })
  })

  describe("mergeActivity", () => {
    it("calls activity.merge and updates round merged_table", async () => {
      mockSendRequest.mockResolvedValueOnce({
        merged: mockMergedRows,
        stats: mockMergeStats,
      })
      await store.getState().mergeActivity("round_1")
      expect(mockSendRequest).toHaveBeenCalledWith(
        "activity.merge",
        { round_id: "round_1" },
        expect.any(Number)
      )
      expect(mockRoundStore.getState().updateRoundField).toHaveBeenCalledWith(
        "round_1",
        "merged_table",
        mockMergedRows
      )
      expect(mockRoundStore.getState().transitionStatus).toHaveBeenCalledWith(
        "round_1",
        "activity_linked"
      )
    })

    it("sets mergeStats after successful merge", async () => {
      mockSendRequest.mockResolvedValueOnce({ merged: mockMergedRows, stats: mockMergeStats })
      await store.getState().mergeActivity("round_1")
      expect(store.getState().lastMergeStats).toEqual(mockMergeStats)
    })

    it("resets lastReplicateStats to null after mergeActivity success (legacy 응답에 replicate_stats 없음)", async () => {
      mockSendRequest.mockResolvedValueOnce({ merged: mockMergedRows, stats: mockMergeStats })
      await store.getState().mergeActivity("round_1")
      expect(store.getState().lastReplicateStats).toBeNull()
    })

    it("transitions to error status on merge failure", async () => {
      mockSendRequest.mockRejectedValueOnce(new Error("WT 없음"))
      await store.getState().mergeActivity("round_1")
      expect(mockRoundStore.getState().transitionStatus).toHaveBeenCalledWith(
        "round_1",
        "error",
        expect.objectContaining({ stage: "merge", message: expect.stringContaining("WT 없음") })
      )
    })
  })

  describe("mergeForEvolvepro", () => {
    it("mergeForEvolvepro_success — RPC 응답으로 state 갱신 (lastMergeStats, lastReplicateStats, merged_table, status)", async () => {
      mockSendRequest.mockResolvedValueOnce({
        merged: mockMergedRows,
        stats: mockMergeStats,
        replicate_stats: mockReplicateStats,
        export_blocked: false,
      })
      await store.getState().mergeForEvolvepro("round_1")
      expect(mockSendRequest).toHaveBeenCalledWith(
        "mame.activity.merge_for_evolvepro",
        expect.objectContaining({ round_id: "round_1", prev_round_evolvepro: {} }),
        expect.any(Number)
      )
      expect(store.getState().lastMergeStats).toEqual(mockMergeStats)
      expect(store.getState().lastReplicateStats).toEqual(mockReplicateStats)
      expect(mockRoundStore.getState().updateRoundField).toHaveBeenCalledWith(
        "round_1",
        "merged_table",
        mockMergedRows
      )
      expect(mockRoundStore.getState().transitionStatus).toHaveBeenCalledWith(
        "round_1",
        "activity_linked"
      )
    })

    it("mergeForEvolvepro_export_blocked — RPC -32004 throw 시 mergeError set, status=error", async () => {
      mockSendRequest.mockRejectedValueOnce(new Error("export blocked: label swap detected"))
      await store.getState().mergeForEvolvepro("round_1")
      expect(store.getState().mergeError).toContain("export blocked")
      expect(mockRoundStore.getState().transitionStatus).toHaveBeenCalledWith(
        "round_1",
        "error",
        expect.objectContaining({ stage: "merge" })
      )
    })

    it("mergeForEvolvepro_does_not_affect_legacy_mergeActivity — mergeActivity 호출 후 lastReplicateStats가 명시 null", async () => {
      // 먼저 mergeForEvolvepro로 lastReplicateStats 채움
      mockSendRequest.mockResolvedValueOnce({
        merged: mockMergedRows,
        stats: mockMergeStats,
        replicate_stats: mockReplicateStats,
        export_blocked: false,
      })
      await store.getState().mergeForEvolvepro("round_1")
      expect(store.getState().lastReplicateStats).toEqual(mockReplicateStats)

      // 이후 legacy mergeActivity 호출 — lastReplicateStats는 null로 리셋되어야 함
      mockSendRequest.mockResolvedValueOnce({ merged: mockMergedRows, stats: mockMergeStats })
      await store.getState().mergeActivity("round_1")
      expect(store.getState().lastReplicateStats).toBeNull()
    })
  })

  describe("exportEvolveproCsv", () => {
    it("calls activity.export_evolvepro_csv RPC", async () => {
      mockSendRequest.mockResolvedValueOnce({ path: "/output.csv" })
      await store.getState().exportEvolveproCsv("round_1", "/output.csv")
      expect(mockSendRequest).toHaveBeenCalledWith(
        "activity.export_evolvepro_csv",
        { round_id: "round_1", path: "/output.csv" },
        expect.any(Number)
      )
    })

    it("sets isExporting false after success", async () => {
      mockSendRequest.mockResolvedValueOnce({})
      await store.getState().exportEvolveproCsv("round_1", "/out.csv")
      expect(store.getState().isExporting).toBe(false)
    })
  })
})
