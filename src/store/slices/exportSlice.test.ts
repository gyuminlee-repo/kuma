/**
 * exportSlice.test.ts — Task 3.3 단위 테스트
 * TDD: workspace snapshot schema_version 0.3 + rounds 직렬화/역직렬화
 */

import { describe, it, expect, vi, beforeEach } from "vitest"

// ─── ipc-kuro mock ───────────────────────────────────────────────────────────
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))

// ─── roundStore mock ─────────────────────────────────────────────────────────
const mockRounds = [
  {
    id: "round_1",
    n: 1,
    created_at: "2026-05-04T00:00:00.000Z",
    status: "design" as const,
    error_info: null,
    plate_meta: { plates: [] },
    design: {},
    genotype: {},
    activity: null,
    merged_table: [],
  },
]

vi.mock("@/store/round/roundSlice", () => ({
  useRoundStore: {
    getState: () => ({
      rounds: mockRounds,
      active_round_id: "round_1",
    }),
  },
}))

import { createExportSlice } from "./exportSlice"
import type { WorkspaceV3 } from "@/types/models"

// 최소 Zustand store 생성 helper
function makeStore() {
  // zustand create를 직접 사용하지 않고 StateCreator를 직접 호출하여 단위 테스트
  const state: Record<string, unknown> = {
    // 필수 최소 상태 (AppState 의존성)
    fastaPath: "/test/sequence.fa",
    mutationInputMode: "text",
    mutationText: "F89W",
    evolveproCsvPath: "",
    selectedGene: "gene1",
    codonStrategy: "closest",
    maxPrimers: 95,
    designResults: [],
    successCount: 0,
    totalCount: 0,
    failedMutations: [],
    plateMappings: [],
    dedupInfo: {},
    tableSorting: [],
    manuallySwapped: {},
    customCandidates: {},
    selectedPolymerase: "Benchling",
    tmFwdTarget: 62,
    tmRevTarget: 58,
    tmOverlapTarget: 42,
    gcMin: 40,
    gcMax: 60,
    primerLenEnabled: true,
    fwdLenMin: 17,
    fwdLenMax: 39,
    revLenMin: 19,
    revLenMax: 27,
    fillOnFailure: true,
    tmTolerance: 3.0,
    uniprotAccession: "",
    domains: [],
    disabledDomains: [],
    domainDiversityEnabled: true,
    domainStrategy: "proportional",
    domainOverlapPolicy: "first",
    linkerHandling: "include",
    domainQuotaMin: 1,
    paretoDiversityEnabled: true,
    entropyWeightEnabled: true,
    entropyWeight: 0.3,
    paretoPoolMultiplier: 2.0,
    distanceMode: "auto",
    benchmarkTopPercentile: 10,
    benchmarkRandomTrials: 100,
    benchmarkRandomSeed: null,
    autoRedesignOnLoad: true,
    saveCache: true,
    organism: "ecoli",
    pipelineMode: true,
    positionDiversityEnabled: true,
    maxPerPosition: 1,
    evolveproRound: 1,
    roundSize: 96,
    overlapMode: "partial",
    evolveproTotalCount: 0,
    evolveproFilteredCount: null,
    evolveproParetoExchanges: null,
    evolveproStepStats: null,
    benchmarkResults: null,
    domainStats: {},
    rescuedMutations: [],
    rescueStats: { pool_cascade: 0, auto_relax: 0, positions_attempted: 0, pool_variants_tried: 0 },
    rescuedMutationDetails: [],
    yPredMap: {},
    poolVariants: [],
  }

  const set = (updater: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    const updates = typeof updater === "function" ? updater(state) : updater
    Object.assign(state, updates)
  }
  const get = () => state

  const slice = createExportSlice(
    set as Parameters<typeof createExportSlice>[0],
    get as unknown as Parameters<typeof createExportSlice>[1],
    {} as Parameters<typeof createExportSlice>[2]
  )
  return { state, slice }
}

describe("exportSlice — schema_version 0.3", () => {
  let store: ReturnType<typeof makeStore>

  beforeEach(() => {
    store = makeStore()
  })

  it("getWorkspaceSnapshot includes schema_version 0.3", () => {
    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3
    expect(snap.schema_version).toBe("0.3")
  })

  it("getWorkspaceSnapshot includes rounds array", () => {
    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3
    expect(snap.rounds).toBeDefined()
    expect(Array.isArray(snap.rounds)).toBe(true)
    expect(snap.rounds).toHaveLength(1)
    expect(snap.rounds[0].id).toBe("round_1")
  })

  it("getWorkspaceSnapshot includes active_round_id", () => {
    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3
    expect(snap.active_round_id).toBe("round_1")
  })

  it("restoreWorkspace rejects schema_version < 0.3 (v2)", async () => {
    const oldWorkspace = {
      version: 2 as const,
      inputs: { fastaPath: "", mutationInputMode: "text" as const, mutationText: "", evolveproCsvPath: "", selectedGene: "" },
      settings: { codonStrategy: "closest" as const, maxPrimers: 95, tmFwdTarget: 62, tmRevTarget: 58, tmOverlapTarget: 42, gcMin: 40, gcMax: 60 },
      results: { designResults: [], successCount: 0, totalCount: 0, failedMutations: [], plateMappings: [], dedupInfo: {}, manuallySwapped: {}, customCandidates: {} },
      ui: { tableSorting: [] },
    }
    await expect(store.slice.restoreWorkspace(oldWorkspace)).rejects.toThrow(/v0\.3 이전/)
  })

  it("restoreWorkspace rejects v1 workspace", async () => {
    const oldWorkspace = {
      version: 1 as const,
      fastaPath: "",
      mutationInputMode: "text" as const,
      mutationText: "",
      evolveproCsvPath: "",
      selectedGene: "",
      codonStrategy: "closest" as const,
      maxPrimers: 95,
      designResults: [],
      successCount: 0,
      totalCount: 0,
      failedMutations: [],
      plateMappings: [],
      dedupInfo: {},
      tableSorting: [],
      manuallySwapped: {},
      customCandidates: {},
      tmFwdTarget: 62,
      tmRevTarget: 58,
      tmOverlapTarget: 42,
      gcMin: 40,
      gcMax: 60,
    }
    await expect(store.slice.restoreWorkspace(oldWorkspace)).rejects.toThrow(/v0\.3 이전/)
  })

  it("getWorkspaceSnapshot still includes kuro inputs (backward compat)", () => {
    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3
    expect(snap.inputs).toBeDefined()
    expect(snap.inputs.fastaPath).toBe("/test/sequence.fa")
  })
})
