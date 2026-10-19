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
import { createDiversitySlice } from "./diversitySlice"
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
    requireNetworkConsent: vi.fn().mockResolvedValue(true),
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
  const diversity = createDiversitySlice(
    set as Parameters<typeof createDiversitySlice>[0],
    get as Parameters<typeof createDiversitySlice>[1],
    {} as Parameters<typeof createDiversitySlice>[2],
  )
  Object.assign(state, diversity, slice, { ...state })
  return { state, slice, diversity }
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

  it.each(["success", "failure"] as const)(
    "ignores an old CSV %s while a new user structure loads",
    async (outcome) => {
      const csv: { resolve?: (value: unknown) => void; reject?: (error: Error) => void } = {}
      const file: { resolve?: (value: unknown) => void } = {}
      const oldResponse = new Promise((resolve, reject) => { csv.resolve = resolve; csv.reject = reject })
      const fileResponse = new Promise((resolve) => { file.resolve = resolve })
      const result = { variants: ["A2V"], y_preds: [1], total_count: 3, selected_count: 1,
        structure_coordinates_used: true, structure_frame_mismatch: false }
      mockSend.mockImplementation(((method: string) =>
        method === "load_structure_file" ? fileResponse : Promise.resolve(result)) as never)
      mockSend.mockReturnValueOnce(oldResponse as never)
      const { state, slice, diversity } = makeStore()
      state.strictSpatialEnabled = false
      state.structure3dState = "active"

      const oldLoad = slice.loadEvolveproCsv("/fake/file.csv")
      const fileLoad = diversity.loadStructureFile("/fake/new.pdb")
      expect(state.structureLoading).toBe(true)
      if (outcome === "success") csv.resolve?.({ ...result, structure_frame_mismatch: true })
      else csv.reject?.(new Error("[-32010] Strict spatial source structure is unavailable"))
      if (outcome === "failure") await expect(oldLoad).rejects.toThrow()
      else await oldLoad
      expect(state.structure3dState).toBe("off")
      file.resolve?.({ success: true, accession: "file:new", residues: 10 })
      await fileLoad

      expect(state.structureAccession).toBe("file:new")
      expect(state.structure3dState).toBe("active")
      expect(state.strictSpatialError).toBeNull()
    },
  )

  it.each(["1d", "auto"] as const)(
    "keeps a CSV loaded during a failed structure request in %s mode",
    async (distanceMode) => {
      const file: { resolve?: (value: unknown) => void } = {}
      const fileResponse = new Promise((resolve) => { file.resolve = resolve })
      const result = { variants: ["A2V"], y_preds: [1], total_count: 3, selected_count: 1,
        structure_coordinates_used: false, structure_frame_mismatch: false }
      mockSend.mockImplementation(((method: string) =>
        method === "load_structure_file" ? fileResponse : Promise.resolve(result)) as never)
      const { state, slice, diversity } = makeStore()
      Object.assign(state, { strictSpatialEnabled: false, structuralDiversityEnabled: false,
        paretoDiversityEnabled: true, distanceMode })

      const fileLoad = diversity.loadStructureFile("/fake/broken.pdb")
      await slice.loadEvolveproCsv("/fake/file.csv")
      file.resolve?.({ success: false, error: "synthetic unreadable structure" })
      await fileLoad

      expect(state.mutationText).toBe("A2V")
      expect(state.evolveproSelectedVariants).toEqual(["A2V"])
      expect(state.structureLoading).toBe(false)
      expect(state.structureAccession).toBe("")
    },
  )
})
