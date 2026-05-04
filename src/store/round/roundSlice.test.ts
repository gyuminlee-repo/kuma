/**
 * roundSlice.test.ts — Task 3.1 + Task 5.2 단위 테스트
 * TDD: 실패 테스트 먼저 작성
 *
 * Task 5.2: handoffNextRound 본 구현 검증
 * - happy path: prevRound exported + newRound design + active round 변경
 * - loadRoundActivity 실패 시 rollback
 * - merged_table 비어있는 prevRound 시 fail-safe
 * - onHandoffSuccess 콜백 호출
 */

import { describe, it, expect, beforeEach, vi } from "vitest"
import { createRoundStore } from "./roundSlice"
import type { MergedRow } from "@/types/mame/activity"

describe("roundSlice", () => {
  let store: ReturnType<typeof createRoundStore>

  beforeEach(() => {
    store = createRoundStore()
  })

  it("addRound creates new round with status=design", () => {
    const id = store.getState().addRound({ plate_meta: { plates: [] } })
    const state = store.getState()
    expect(state.rounds).toHaveLength(1)
    expect(state.rounds[0].status).toBe("design")
    expect(state.rounds[0].n).toBe(1)
    expect(id).toBe("round_1")
  })

  it("transitionStatus updates round status", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "activity_linked")
    expect(store.getState().rounds[0].status).toBe("activity_linked")
  })

  it("addRound increments n", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().addRound({ plate_meta: { plates: [] } })
    const state = store.getState()
    expect(state.rounds[1].n).toBe(2)
    expect(state.rounds[1].id).toBe("round_2")
  })

  it("addRound sets active_round_id to new round", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    expect(store.getState().active_round_id).toBe("round_1")
  })

  it("setActiveRound changes active round", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().setActiveRound("round_1")
    expect(store.getState().active_round_id).toBe("round_1")
  })

  it("updateRoundField updates specific field", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().updateRoundField("round_1", "merged_table", [
      {
        plate_id: "P01",
        well_id: "A01",
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
    ])
    expect(store.getState().rounds[0].merged_table).toHaveLength(1)
  })

  it("transitionStatus to error sets error_info when provided", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "error", {
      stage: "merge",
      message: "WT 없음",
      occurred_at: new Date().toISOString(),
    })
    const round = store.getState().rounds[0]
    expect(round.status).toBe("error")
    expect(round.error_info).not.toBeNull()
    expect(round.error_info?.stage).toBe("merge")
  })

  it("transitionStatus on unknown id is a no-op", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    expect(() =>
      store.getState().transitionStatus("nonexistent", "design")
    ).not.toThrow()
    expect(store.getState().rounds[0].status).toBe("design")
  })
})

// ─── Task 5.2: handoffNextRound ──────────────────────────────────────────────

function makeActivityRow(mutation: string, log2_fc: number): MergedRow {
  return {
    plate_id: "P01",
    well_id: "B01",
    mutation,
    mutation_source: "kuro_design",
    expected_mutation: mutation,
    called_mutation: mutation,
    ngs_success: true,
    activity_raw_mean: 2.0,
    activity_raw_sd: 0.1,
    activity_replicates: [1.9, 2.1],
    replicate_n: 2,
    fold_change: Math.pow(2, log2_fc),
    log2_fc,
  }
}

describe("roundSlice.handoffNextRound", () => {
  let store: ReturnType<typeof createRoundStore>

  beforeEach(() => {
    store = createRoundStore()
  })

  it("happy path: prevRound becomes exported, new round is design, active round changes", () => {
    const loadRoundActivity = vi.fn().mockReturnValue({ ok: true, warnings: [] })

    // setup round_1 with activity data
    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "activity_linked")
    store.getState().updateRoundField("round_1", "merged_table", [
      makeActivityRow("F89W", 0.99),
      makeActivityRow("L70V", -0.50),
    ])

    const result = store.getState().handoffNextRound("round_1", { loadRoundActivity })

    expect(result.ok).toBe(true)
    expect(result.newRoundId).toBe("round_2")

    const state = store.getState()
    // prevRound exported
    expect(state.rounds[0].status).toBe("exported")
    // new round created with status=design
    expect(state.rounds[1].status).toBe("design")
    expect(state.rounds[1].n).toBe(2)
    // active round updated to new round
    expect(state.active_round_id).toBe("round_2")
    // loadRoundActivity called with prevRound
    expect(loadRoundActivity).toHaveBeenCalledOnce()
    expect(loadRoundActivity).toHaveBeenCalledWith(
      expect.objectContaining({ id: "round_1" })
    )
  })

  it("rolls back new round when loadRoundActivity returns ok=false", () => {
    const loadRoundActivity = vi.fn().mockReturnValue({
      ok: false,
      warnings: ["0 rows after filter (ngs_success && non-WT && log2_fc not null)"],
    })

    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "activity_linked")

    const result = store.getState().handoffNextRound("round_1", { loadRoundActivity })

    expect(result.ok).toBe(false)
    expect(result.warnings.length).toBeGreaterThan(0)

    const state = store.getState()
    // only round_1 remains (rollback)
    expect(state.rounds).toHaveLength(1)
    // prevRound should NOT be exported (rollback)
    expect(state.rounds[0].status).toBe("activity_linked")
    // active round unchanged
    expect(state.active_round_id).toBe("round_1")
  })

  it("fail-safe: returns ok=false when prevRoundId not found", () => {
    const loadRoundActivity = vi.fn()

    const result = store.getState().handoffNextRound("nonexistent", { loadRoundActivity })

    expect(result.ok).toBe(false)
    expect(result.warnings).toContain("prevRound not found: nonexistent")
    expect(loadRoundActivity).not.toHaveBeenCalled()
  })

  it("fail-safe: returns ok=false when merged_table is empty", () => {
    const loadRoundActivity = vi.fn().mockReturnValue({ ok: false, warnings: ["0 rows after filter (ngs_success && non-WT && log2_fc not null)"] })

    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "activity_linked")
    // merged_table is empty (default)

    const result = store.getState().handoffNextRound("round_1", { loadRoundActivity })

    expect(result.ok).toBe(false)
    const state = store.getState()
    expect(state.rounds).toHaveLength(1)
  })

  it("calls onHandoffSuccess callback on success", () => {
    const loadRoundActivity = vi.fn().mockReturnValue({ ok: true, warnings: [] })
    const onHandoffSuccess = vi.fn()

    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "activity_linked")
    store.getState().updateRoundField("round_1", "merged_table", [
      makeActivityRow("F89W", 0.99),
    ])

    store.getState().handoffNextRound("round_1", { loadRoundActivity, onHandoffSuccess })

    expect(onHandoffSuccess).toHaveBeenCalledOnce()
  })

  it("does not call onHandoffSuccess when loadRoundActivity fails", () => {
    const loadRoundActivity = vi.fn().mockReturnValue({ ok: false, warnings: ["no rows"] })
    const onHandoffSuccess = vi.fn()

    store.getState().addRound({ plate_meta: { plates: [] } })
    store.getState().transitionStatus("round_1", "activity_linked")

    store.getState().handoffNextRound("round_1", { loadRoundActivity, onHandoffSuccess })

    expect(onHandoffSuccess).not.toHaveBeenCalled()
  })

  it("new round inherits plate_meta from prevRound", () => {
    const loadRoundActivity = vi.fn().mockReturnValue({ ok: true, warnings: [] })
    const plateMeta = { plates: [{ plate_id: "P01", wt_wells: ["A01"], control_wells: [] }] }

    store.getState().addRound({ plate_meta: plateMeta })
    store.getState().transitionStatus("round_1", "activity_linked")
    store.getState().updateRoundField("round_1", "merged_table", [
      makeActivityRow("F89W", 0.99),
    ])

    store.getState().handoffNextRound("round_1", { loadRoundActivity })

    const newRound = store.getState().rounds[1]
    expect(newRound.plate_meta).toEqual(plateMeta)
  })
})
