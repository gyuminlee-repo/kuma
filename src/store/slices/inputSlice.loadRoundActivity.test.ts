/**
 * inputSlice.loadRoundActivity.test.ts — Task 5.1 TDD
 *
 * loadRoundActivity(prevRound) 동작 검증:
 * - merged_table 필터 (ngs_success && mutation && mutation !== "WT" && log2_fc !== null)
 * - mutationInputMode = "evolvepro" 전환
 * - mutationText = variants.join("\n") (loadEvolveproCsv 동일 hydration 패턴)
 * - yPredMap 빌드
 * - evolveproTotalCount = filtered 수
 * - 캐시(evolveproFilteredCount, evolveproParetoExchanges, evolveproStepStats) 초기화
 * - 0 rows → ok=false, 상태 변경 없음
 * - WT 제외
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.5
 * Note: 스펙 step 5 (mutationText="") 는 현재 store 구조 상 mutationText가 evolvepro
 *       variants 표시에 사용되므로 variants.join("\n")으로 완화 (loadEvolveproCsv 동일 시맨틱)
 */

import { describe, it, expect, vi, beforeEach } from "vitest"
import type { Round } from "@/types/round"
import type { MergedRow } from "@/types/mame/activity"
import type { EvolveproStepStats } from "@/types/models"

// ─── ipc-kuro mock ────────────────────────────────────────────────────────────
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))

// ─── Tauri path mock ──────────────────────────────────────────────────────────
vi.mock("@tauri-apps/api/path", () => ({
  resolveResource: vi.fn(),
}))

import { createInputSlice } from "./inputSlice"
import type { AppState } from "../types"

// ─── minimal store helper ────────────────────────────────────────────────────

function makeInputStore() {
  const state: Record<string, unknown> = {
    mutationInputMode: "text",
    mutationText: "",
    parsedMutations: [],
    parseErrors: [],
    evolveproCsvPath: "",
    evolveproTotalCount: 0,
    evolveproFilteredCount: null,
    evolveproParetoExchanges: null,
    evolveproStepStats: null,
    yPredMap: {},
    // diversity fields referenced by slice
    evolveproMode: "pipeline" as const,
    positionDiversityEnabled: true,
    maxPerPosition: 1,
    domainDiversityEnabled: true,
    domains: [],
    disabledDomains: [],
    domainStrategy: "proportional",
    domainOverlapPolicy: "first",
    linkerHandling: "include",
    domainQuotaMin: 1,
    paretoDiversityEnabled: false,
    structuralDiversityEnabled: false,
    structuralKappa: 0.3,
    entropyWeightEnabled: false,
    entropyWeight: 0.3,
    paretoPoolMultiplier: 2.0,
    distanceMode: "auto",
    uniprotAccession: "",
    evolveproRound: 0,
    roundSize: 96,
    maxPrimers: 95,
    domainStats: {},
    poolVariants: [],
    statusMessage: "",
  }

  const set = (updater: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    const updates = typeof updater === "function" ? updater(state) : updater
    Object.assign(state, updates)
  }
  const get = () => state as unknown as AppState

  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  )

  return { state, slice }
}

// ─── fixtures ─────────────────────────────────────────────────────────────────

function makeRow(overrides: Partial<MergedRow>): MergedRow {
  return {
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
    ...overrides,
  }
}

function makeRound(merged_table: MergedRow[]): Round {
  return {
    id: "round_1",
    n: 1,
    created_at: "2026-05-04T00:00:00.000Z",
    status: "activity_linked",
    error_info: null,
    plate_meta: { plates: [] },
    design: {},
    genotype: {},
    activity: null,
    merged_table,
  }
}

describe("inputSlice.loadRoundActivity", () => {
  let store: ReturnType<typeof makeInputStore>

  beforeEach(() => {
    store = makeInputStore()
  })

  it("happy path: hydrates variants from merged_table, sets evolvepro mode", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99, well_id: "B03" }),
      makeRow({ mutation: "L70V", log2_fc: -0.50, well_id: "G05" }),
    ])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(true)
    expect(result.warnings).toHaveLength(0)

    expect(store.state.mutationInputMode).toBe("evolvepro")
    // mutationText = variants.join("\n") for KURO design compatibility
    expect(store.state.mutationText).toBe("F89W\nL70V")
    expect((store.state.yPredMap as Record<string, number>)["F89W"]).toBeCloseTo(0.99)
    expect((store.state.yPredMap as Record<string, number>)["L70V"]).toBeCloseTo(-0.50)
    expect(store.state.evolveproTotalCount).toBe(2)
  })

  it("excludes WT rows", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99, well_id: "B03" }),
      makeRow({ mutation: "WT", log2_fc: 0.0, well_id: "A01" }),
    ])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(true)
    expect(store.state.mutationText).toBe("F89W")
    expect(store.state.evolveproTotalCount).toBe(1)
    expect(Object.keys(store.state.yPredMap as Record<string, number>)).not.toContain("WT")
  })

  it("excludes ngs_success=false rows", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99 }),
      makeRow({ mutation: "R45K", log2_fc: 0.5, ngs_success: false, well_id: "C03" }),
    ])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(true)
    expect(store.state.mutationText).toBe("F89W")
    expect(store.state.evolveproTotalCount).toBe(1)
  })

  it("excludes rows with log2_fc=null", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99 }),
      makeRow({ mutation: "K20A", log2_fc: null, well_id: "D04" }),
    ])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(true)
    expect(store.state.mutationText).toBe("F89W")
    expect(store.state.evolveproTotalCount).toBe(1)
  })

  it("excludes rows with mutation=null (activity_only)", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99 }),
      makeRow({ mutation: null, log2_fc: 0.5, mutation_source: "activity_only", well_id: "E05" }),
    ])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(true)
    expect(store.state.mutationText).toBe("F89W")
  })

  it("returns ok=false for empty merged_table, does not mutate state", () => {
    store.slice.setMutationText("EXISTING_TEXT")
    store.slice.setMutationInputMode("text")

    const prevRound = makeRound([])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(false)
    expect(result.warnings).toContain("0 rows after filter (ngs_success && non-WT && log2_fc not null)")

    // state must remain unchanged
    expect(store.state.mutationInputMode).toBe("text")
    expect(store.state.mutationText).toBe("EXISTING_TEXT")
  })

  it("returns ok=false when all rows are filtered out, does not mutate state", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "WT", log2_fc: 0.0 }),
      makeRow({ mutation: "R45K", log2_fc: null }),
      makeRow({ mutation: "L70V", log2_fc: 0.5, ngs_success: false }),
    ])

    const result = store.slice.loadRoundActivity(prevRound)

    expect(result.ok).toBe(false)
    expect(result.warnings.length).toBeGreaterThan(0)
    expect(store.state.mutationInputMode).toBe("text")
  })

  it("clears diversity cache fields (evolveproFilteredCount, evolveproParetoExchanges, evolveproStepStats) on success", () => {
    // pre-populate stale cache from previous round
    store.state.evolveproFilteredCount = 42
    store.state.evolveproParetoExchanges = 5
    store.state.evolveproStepStats = { steps: [] } as unknown as EvolveproStepStats

    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99 }),
    ])

    store.slice.loadRoundActivity(prevRound)

    expect(store.state.evolveproFilteredCount).toBeNull()
    expect(store.state.evolveproParetoExchanges).toBeNull()
    expect(store.state.evolveproStepStats).toBeNull()
  })

  it("sets evolveproCsvPath to empty string (memory hydrate, no CSV file)", () => {
    store.state.evolveproCsvPath = "/old/path/round1.csv"

    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99 }),
    ])

    store.slice.loadRoundActivity(prevRound)

    expect(store.state.evolveproCsvPath).toBe("")
  })

  it("does not set statusMessage to error on success (sets informational message)", () => {
    const prevRound = makeRound([
      makeRow({ mutation: "F89W", log2_fc: 0.99 }),
      makeRow({ mutation: "L70V", log2_fc: -0.50, well_id: "G05" }),
    ])

    store.slice.loadRoundActivity(prevRound)

    const msg = store.state.statusMessage as string
    expect(msg).not.toMatch(/error|fail/i)
    expect(msg).toMatch(/2/)  // should mention count
  })
})
