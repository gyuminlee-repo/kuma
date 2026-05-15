/**
 * inputSlice.loadSampleData.test.ts
 *
 * loadSampleData() 동작 검증 (Item 1, PI 2026-05-15):
 * - EGFP FASTA 로드 후 text 모드로 전환 + 데모 mutationText 채움
 * - mutationInputMode 무관하게 동일 동작 (Item 1: wizard Next 통과용 단일 경로)
 * - loadSequence 실패(seqInfo=null) 시 후속 텍스트 채움 안 됨, 상태 메시지 보존
 * - 리소스 경로 resolveResource로 해석
 */

import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))

vi.mock("@tauri-apps/api/path", () => ({
  resolveResource: vi.fn((p: string) => Promise.resolve(`/resolved/${p}`)),
}))

vi.mock("@tauri-apps/plugin-fs", () => ({
  readTextFile: vi.fn(() =>
    Promise.resolve("variant,y_pred\nN267F,0.99\nQ163W,0.98\n"),
  ),
}))

import { sendRequest } from "@/lib/ipc-kuro"
import { resolveResource } from "@tauri-apps/api/path"
import { createInputSlice } from "./inputSlice"
import type { AppState } from "../types"

function makeStore(overrides: Record<string, unknown> = {}) {
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
    pipelineMode: false,
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
    seqInfo: null,
    selectedGene: "",
    statusMessage: "",
    loadSequence: vi.fn(),
    loadEvolveproCsv: vi.fn(),
    setMaxPrimers: vi.fn(),
    ...overrides,
  }
  const set = (
    updater: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>),
  ) => {
    const u = typeof updater === "function" ? updater(state) : updater
    Object.assign(state, u)
  }
  const get = () => state as unknown as AppState
  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  )
  // expose slice methods, then re-apply caller overrides so they aren't clobbered by slice initial state
  Object.assign(state, slice, overrides)
  return { state, slice }
}

describe("inputSlice.loadSampleData", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("loads EGFP FASTA, forces text mode, and populates demo mutationText", async () => {
    const loadSequence = vi.fn(async () => {
      // simulate successful sequence load
      ;(store.state as { seqInfo: unknown }).seqInfo = {
        header: "x",
        seq_length: 720,
        genes: [
          { gene: "egfp", aa_length: 239, translation: "M", cds_start: 1, cds_end: 720 },
        ],
      }
    })
    const loadEvolveproCsv = vi.fn(async () => {})
    const store = makeStore({ loadSequence, loadEvolveproCsv })

    await store.slice.loadSampleData()

    expect(resolveResource).toHaveBeenCalledWith("samples/egfp.fa")
    expect(loadSequence).toHaveBeenCalledWith("/resolved/samples/egfp.fa")
    // Item 1: CSV loader is intentionally skipped (CSV is invalid for EGFP).
    expect(loadEvolveproCsv).not.toHaveBeenCalled()
    expect(store.state.mutationInputMode).toBe("text")
    expect(store.state.mutationText).toBe("L65A, F100A, N150A, H200A")
  })

  it("aborts before CSV load if loadSequence silently failed (seqInfo stays null)", async () => {
    const loadSequence = vi.fn(async () => {
      // simulate the swallowed-error path: seqInfo never gets set, statusMessage carries the cause
      ;(store.state as { statusMessage: string }).statusMessage =
        "Sequence file load failed: bundle missing"
    })
    const loadEvolveproCsv = vi.fn(async () => {})
    const store = makeStore({ loadSequence, loadEvolveproCsv })

    await store.slice.loadSampleData()

    expect(loadSequence).toHaveBeenCalledTimes(1)
    expect(loadEvolveproCsv).not.toHaveBeenCalled()
    expect(store.state.statusMessage).toBe("Sequence file load failed: bundle missing")
  })

  it("uses generic catch when resolveResource throws", async () => {
    ;(resolveResource as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("resource missing"),
    )
    const loadSequence = vi.fn()
    const loadEvolveproCsv = vi.fn()
    const store = makeStore({ loadSequence, loadEvolveproCsv })

    await store.slice.loadSampleData()

    expect(loadSequence).not.toHaveBeenCalled()
    expect(loadEvolveproCsv).not.toHaveBeenCalled()
    expect(store.state.statusMessage).toMatch(/Sample load failed/)
  })
})

// suppress unused-import lint
void sendRequest
