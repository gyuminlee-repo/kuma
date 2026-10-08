/**
 * inputSlice.evolveproSelection.test.ts
 *
 * evolveproSelectedVariants / evolveproRankedCandidates / evolveproExtraExposed
 * 상태 관리 및 setEvolveproVariantSelected / setEvolveproExtraExposed setter 검증.
 */

import { describe, it, expect, vi, beforeEach } from "vitest"
import type { AppState } from "../types"

// ─── mock external deps ───────────────────────────────────────────────────────
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))
vi.mock("@tauri-apps/api/path", () => ({ resolveResource: vi.fn() }))

import { createInputSlice } from "./inputSlice"
import { sendRequest } from "@/lib/ipc-kuro"

// ─── minimal store helper ─────────────────────────────────────────────────────

function makeStore() {
  const state: Record<string, unknown> = {
    mutationInputMode: "evolvepro",
    mutationText: "F89W\nL70V\nM1A",
    parsedMutations: [],
    parseErrors: [],
    evolveproCsvPath: "/fake/file.csv",
    evolveproTotalCount: 3,
    evolveproFilteredCount: null,
    evolveproParetoExchanges: null,
    evolveproStepStats: null,
    yPredMap: { F89W: 0.9, L70V: 0.5, M1A: 0.3 },
    evolveproMode: "topN" as const,
    evolveproRankedCandidates: [
      { variant: "F89W", y_pred: 0.9, aa_position: 89 },
      { variant: "L70V", y_pred: 0.5, aa_position: 70 },
      { variant: "M1A", y_pred: 0.3, aa_position: 1 },
    ],
    evolveproSelectedVariants: ["F89W", "L70V", "M1A"],
    evolveproSelectionManual: false,
    evolveproExtraExposed: 10,
    positionDiversityEnabled: false,
    maxPerPosition: 1,
    domainDiversityEnabled: false,
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
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
    evolveproScoreOrder: "desc" as const,
    evolveproSheetName: null,
    evolveproPreview: null,
    evolveproUsedVariantColumn: null,
    evolveproUsedScoreColumn: null,
    seqInfo: null,
    selectedGene: "",
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

// ─── tests ────────────────────────────────────────────────────────────────────

describe("inputSlice evolvepro selection state", () => {
  let store: ReturnType<typeof makeStore>

  beforeEach(() => {
    store = makeStore()
  })

  it("initial selection includes all three variants", () => {
    expect(store.state.evolveproSelectedVariants).toEqual(["F89W", "L70V", "M1A"])
  })

  it("setEvolveproVariantSelected(variant, false) removes from selection", () => {
    store.slice.setEvolveproVariantSelected("L70V", false)
    expect(store.state.evolveproSelectedVariants).not.toContain("L70V")
    expect(store.state.evolveproSelectedVariants).toContain("F89W")
    expect(store.state.evolveproSelectedVariants).toContain("M1A")
  })

  it("setEvolveproVariantSelected(variant, true) adds to selection without duplicates", () => {
    store.slice.setEvolveproVariantSelected("L70V", false)
    store.slice.setEvolveproVariantSelected("L70V", true)
    const selected = store.state.evolveproSelectedVariants as string[]
    expect(selected.filter((v) => v === "L70V")).toHaveLength(1)
  })

  it("setEvolveproVariantSelected(already-selected, true) is idempotent", () => {
    store.slice.setEvolveproVariantSelected("F89W", true)
    const selected = store.state.evolveproSelectedVariants as string[]
    expect(selected.filter((v) => v === "F89W")).toHaveLength(1)
  })

  it("setEvolveproExtraExposed updates the value", () => {
    store.slice.setEvolveproExtraExposed(25)
    expect(store.state.evolveproExtraExposed).toBe(25)
  })

  it("setEvolveproExtraExposed clamps negative to 0", () => {
    store.slice.setEvolveproExtraExposed(-5)
    expect(store.state.evolveproExtraExposed).toBe(0)
  })

  it("setMutationInputMode sets mode without clearing evolvepro state", () => {
    store.slice.setMutationInputMode("evolvepro")
    // Mode is updated but selection and ranked candidates are preserved
    expect(store.state.mutationInputMode).toBe("evolvepro")
    expect(store.state.evolveproSelectedVariants).toEqual(["F89W", "L70V", "M1A"])
    expect(store.state.evolveproRankedCandidates).toHaveLength(3)
  })
})

// Run Design reloads the CSV with preserveSelection and a topN of at least the
// design count. Keeping the load-time selection there is what held a design at
// the count the CSV was first loaded with.
describe("preserving reload and the design count", () => {
  const variants = ["V1", "V2", "V3", "V4", "V5", "V6"]
  const response = {
    variants,
    y_preds: variants.map((_, i) => 1 - i / 10),
    total_count: 8,
    ranked_candidates: [...variants, "V7", "V8"].map((v, i) => ({ variant: v, y_pred: 1 - i / 10, aa_position: i + 2 })),
    pool_variants: [],
    filtered_count: 0,
    domain_stats: null,
    pareto_replaced: null,
  }

  it("re-derives a seeded selection at the current count", async () => {
    const store = makeStore()
    store.state.maxPrimers = 4
    vi.mocked(sendRequest).mockResolvedValueOnce(response as never)
    await store.slice.loadEvolveproCsv("/fake/file.csv", 6, false, true)
    expect(store.state.evolveproSelectedVariants).toEqual(["V1", "V2", "V3", "V4"])
  })

  it("keeps a hand-set selection", async () => {
    const store = makeStore()
    store.state.maxPrimers = 4
    store.state.evolveproSelectionManual = true
    vi.mocked(sendRequest).mockResolvedValueOnce(response as never)
    await store.slice.loadEvolveproCsv("/fake/file.csv", 6, false, true)
    expect(store.state.evolveproSelectedVariants).toEqual(["F89W", "L70V", "M1A"])
  })

  it("marks picker toggles as hand-set", () => {
    const store = makeStore()
    store.slice.setEvolveproVariantSelected("L70V", false)
    expect(store.state.evolveproSelectionManual).toBe(true)
  })
})
