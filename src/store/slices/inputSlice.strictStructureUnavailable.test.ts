import { beforeEach, describe, expect, it, vi } from "vitest"
import type { AppState } from "../types"

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}))
vi.mock("@tauri-apps/api/path", () => ({ resolveResource: vi.fn() }))
vi.mock("i18next", () => ({
  default: { t: (key: string) => key },
}))

import { createInputSlice } from "./inputSlice"
import { sendRequest } from "@/lib/ipc-kuro"

const mockSend = vi.mocked(sendRequest)

function makeStore() {
  const state: Record<string, unknown> = {
    mutationInputMode: "evolvepro",
    mutationText: "",
    evolveproCsvPath: "/fake/file.csv",
    evolveproMode: "pipeline",
    strictSpatialEnabled: true,
    strictSpatialBudgetMode: "unique_sites",
    strictSpatialSiteCap: null,
    paretoDiversityEnabled: false,
    structuralDiversityEnabled: true,
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
    maxPrimers: 3,
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
    evolveproScoreOrder: "desc",
    evolveproSheetName: null,
    evolveproSelectedVariants: [],
    uniprotAccession: "",
    structureAccession: "ESMFOLD:ABC",
    structureLoaded: true,
    seqInfo: {
      header: ">t",
      seq_length: 10,
      genes: [{ gene: "T", product: "t", cds_start: 1, cds_end: 30, aa_length: 10, translation: "MKTAYIAKQR" }],
    },
    selectedGene: "",
    statusMessage: "",
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

describe("strict spatial load when the structure is unavailable", () => {
  beforeEach(() => mockSend.mockReset())

  it("shows the localized message and the recovery state, not the sidecar's English text", async () => {
    mockSend.mockRejectedValueOnce(new Error("[-32010] Strict spatial source structure is unavailable"))
    const { state, slice } = makeStore()

    await expect(slice.loadEvolveproCsv("/fake/file.csv")).rejects.toThrow()

    expect(state.structure3dState).toBe("frame_mismatch")
    expect(state.strictSpatialError).toBe("strictSpatial.structureNotUsable")
  })
})
