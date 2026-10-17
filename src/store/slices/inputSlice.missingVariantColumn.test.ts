/**
 * inputSlice.missingVariantColumn.test.ts
 *
 * The sidecar refuses an explicit variant column the file does not have
 * (kuma_core/kuro/evolvepro.py:_resolve_evolvepro_columns). Before that it
 * answered with zero variants, which read as an empty file. This pins what the
 * store does with the refusal: the cause reaches the status line, no stale
 * selection survives, and choosing another column sends a different request.
 */

import { describe, it, expect, vi, beforeEach } from "vitest"
import type { AppState } from "../types"

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))
vi.mock("@tauri-apps/api/path", () => ({ resolveResource: vi.fn() }))

import { createInputSlice } from "./inputSlice"
import { sendRequest } from "@/lib/ipc-kuro"

const mockSend = vi.mocked(sendRequest)

const REFUSAL =
  "EVOLVEpro file has no variant column named 'Variantt'. Found: ['Variant', 'y_pred']. "
  + "Pick the variant column from the list above."

function makeStore(overrides: Record<string, unknown> = {}) {
  const state: Record<string, unknown> = {
    mutationInputMode: "evolvepro",
    mutationText: "A10G\nA20G",
    evolveproCsvPath: "/fake/file.csv",
    evolveproMode: "topN",
    paretoDiversityEnabled: false,
    structuralDiversityEnabled: false,
    positionDiversityEnabled: false,
    maxPerPosition: 1,
    domainDiversityEnabled: false,
    domains: [],
    disabledDomains: [],
    domainStrategy: "proportional",
    domainOverlapPolicy: "first",
    linkerHandling: "include",
    domainQuotaMin: 1,
    entropyWeightEnabled: false,
    entropyWeight: 0.3,
    paretoPoolMultiplier: 2.0,
    distanceMode: "auto",
    structuralKappa: 0.3,
    evolveproRound: 0,
    roundSize: 96,
    maxPrimers: 95,
    evolveproVariantColumn: "Variantt",
    evolveproScoreColumn: null,
    evolveproScoreOrder: "desc",
    evolveproSheetName: null,
    evolveproSelectedVariants: ["A10G", "A20G"],
    evolveproTotalCount: 2,
    uniprotAccession: "",
    structureAccession: "",
    structureLoaded: false,
    seqInfo: null,
    selectedGene: "",
    statusMessage: "",
    setMaxPrimers: vi.fn(),
    ...overrides,
  }
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u)
  }
  const get = () => state as unknown as AppState
  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  )
  return { state, slice }
}

function sentParams(index: number): Record<string, unknown> {
  const calls = mockSend.mock.calls.filter((c) => c[0] === "load_evolvepro_csv")
  const call = calls[index]
  if (!call) throw new Error(`load_evolvepro_csv call #${index} was never sent`)
  return call[1] as Record<string, unknown>
}

describe("inputSlice: explicit variant column the file does not have", () => {
  beforeEach(() => {
    mockSend.mockReset()
  })

  it("shows the sidecar's refusal and clears the previous selection", async () => {
    mockSend.mockRejectedValueOnce(new Error(REFUSAL))
    const { state, slice } = makeStore()

    await expect(slice.loadEvolveproCsv("/fake/file.csv")).rejects.toThrow("Variantt")

    expect(sentParams(0).variant_column).toBe("Variantt")
    // The status line carries the requested name and the real headers.
    expect(state.statusMessage).toContain("no variant column named 'Variantt'")
    expect(state.statusMessage).toContain("['Variant', 'y_pred']")
    // Nothing from the earlier load is left looking like this file's result.
    expect(state.mutationText).toBe("")
    expect(state.evolveproSelectedVariants).toEqual([])
    expect(state.evolveproTotalCount).toBe(0)
    // The file stays selected so the column panel can still address it.
    expect(state.evolveproCsvPath).toBe("/fake/file.csv")
  })

  it("re-picking a column after the refusal sends the new name", async () => {
    mockSend.mockRejectedValueOnce(new Error(REFUSAL))
    const { state, slice } = makeStore()
    await expect(slice.loadEvolveproCsv("/fake/file.csv")).rejects.toThrow()

    mockSend.mockResolvedValueOnce({
      variants: ["A10G"],
      y_preds: [0.9],
      total_count: 1,
      selected_count: 1,
      used_variant_column: "Variant",
      used_score_column: "y_pred",
    } as never)
    slice.setEvolveproVariantColumn("Variant")
    await slice.loadEvolveproCsv("/fake/file.csv")

    expect(sentParams(1).variant_column).toBe("Variant")
    expect(state.evolveproUsedVariantColumn).toBe("Variant")
    expect(state.evolveproSelectedVariants).toEqual(["A10G"])
    expect(state.statusMessage).not.toContain("Variantt")
  })

  it("returning to auto-detect omits the column from the request", async () => {
    mockSend.mockResolvedValue({
      variants: [], y_preds: [], total_count: 0, selected_count: 0,
    } as never)
    const { slice } = makeStore()

    slice.setEvolveproVariantColumn(null)
    await slice.loadEvolveproCsv("/fake/file.csv")

    expect(sentParams(0).variant_column).toBeUndefined()
  })
})
