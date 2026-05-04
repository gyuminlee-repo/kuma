/**
 * roundSlice.test.ts — Task 3.1 단위 테스트
 * TDD: 실패 테스트 먼저 작성
 */

import { describe, it, expect, beforeEach } from "vitest"
import { createRoundStore } from "./roundSlice"

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

  it("handoffNextRound is a stub returning null in Phase 3", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    const result = store.getState().handoffNextRound("round_1")
    expect(result).toBeNull()
  })

  it("transitionStatus on unknown id is a no-op", () => {
    store.getState().addRound({ plate_meta: { plates: [] } })
    expect(() =>
      store.getState().transitionStatus("nonexistent", "design")
    ).not.toThrow()
    expect(store.getState().rounds[0].status).toBe("design")
  })
})
