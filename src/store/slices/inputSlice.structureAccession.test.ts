/**
 * inputSlice.structureAccession.test.ts
 *
 * Locks the accession sent to load_evolvepro_csv for 3D selection. A user-loaded
 * structure file lives in structureAccession (file:...), not uniprotAccession,
 * and sending uniprotAccession alone silently dropped the file coordinates,
 * leaving 3D selection on 1-D distance while the panel reported "3D active".
 * The param only appears under pipeline mode + a 3D consumer, so both are set;
 * without them the field is omitted and the assertion would pass vacuously.
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

// Minimal valid EvolveproLoadResult: buildEvolveproLoadStateUpdate only needs
// these fields, and empty variant arrays exercise the wiring without data.
const EMPTY_RESULT = {
  variants: [],
  y_preds: [],
  total_count: 0,
  selected_count: 0,
}

function makeStore(overrides: Record<string, unknown> = {}) {
  const state: Record<string, unknown> = {
    mutationInputMode: "evolvepro",
    mutationText: "",
    evolveproCsvPath: "/fake/file.csv",
    evolveproMode: "pipeline",
    // 3D consumer on so the structure_accession param is emitted.
    paretoDiversityEnabled: true,
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
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
    evolveproScoreOrder: "desc",
    evolveproSheetName: null,
    uniprotAccession: "",
    structureAccession: "",
    structureLoaded: false,
    seqInfo: null,
    selectedGene: "",
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

function sentParams(): Record<string, unknown> {
  const call = mockSend.mock.calls.find((c) => c[0] === "load_evolvepro_csv")
  if (!call) throw new Error("load_evolvepro_csv was never sent")
  return call[1] as Record<string, unknown>
}

describe("inputSlice structure_accession wiring", () => {
  beforeEach(() => {
    mockSend.mockReset()
    mockSend.mockResolvedValue(EMPTY_RESULT as never)
  })

  it("sends the loaded structure file key, not the uniprot accession", async () => {
    // A near-match accession is present but a file was loaded: the file wins.
    const { slice } = makeStore({
      structureAccession: "file:IspS.cif",
      uniprotAccession: "Q50L36",
    })
    await slice.loadEvolveproCsv("/fake/file.csv")
    expect(sentParams().structure_accession).toBe("file:IspS.cif")
  })

  it("falls back to the uniprot accession when no structure file is loaded", async () => {
    const { slice } = makeStore({
      structureAccession: "",
      uniprotAccession: "Q50L36",
    })
    await slice.loadEvolveproCsv("/fake/file.csv")
    expect(sentParams().structure_accession).toBe("Q50L36")
  })

  it("omits structure_accession when neither is set", async () => {
    const { slice } = makeStore({ structureAccession: "", uniprotAccession: "" })
    await slice.loadEvolveproCsv("/fake/file.csv")
    expect(sentParams().structure_accession).toBeUndefined()
  })
})
