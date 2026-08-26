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
import { sendRequest } from "@/lib/ipc-kuro"
import { MAX_MUTATIONS_PER_RUN } from "@/lib/inputThresholds"
import type { PlateMapping, SdmPrimerResult, SequenceInfo, WorkspaceV3 } from "@/types/models"

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
    refDomains: [],
    refDomainsLoading: false,
    refDomainHash: "",
    disabledDomains: [],
    domainDiversityEnabled: true,
    domainStrategy: "proportional",
    domainOverlapPolicy: "first",
    linkerHandling: "include",
    domainQuotaMin: 1,
    paretoDiversityEnabled: true,
    structuralDiversityEnabled: false,
    structuralKappa: 0.3,
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
    evolveproMode: "pipeline" as const,
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
    currentMajor: "design",
    currentSubStep: "design.load",
    evolveproRankedCandidates: [],
    evolveproSelectedVariants: [],
    evolveproExtraExposed: 10,
    resetAll: () => {
      Object.assign(state, {
        designResults: [],
        plateMappings: [],
        dedupInfo: {},
      })
    },
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

function primer(mutation: string, aaPosition: number, reverseSeq = `GCAT${aaPosition}`): SdmPrimerResult {
  return {
    mutation,
    aa_position: aaPosition,
    codon_pos: (aaPosition - 1) * 3,
    forward_seq: `ATGC${aaPosition}`,
    reverse_seq: reverseSeq,
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    candidate_fwd_count: 1,
    candidate_rev_count: 1,
    candidate_count: 1,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 3,
    has_offtarget: false,
    penalty: aaPosition,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "GAA",
    mt_codon: "GAT",
    overlap_seq: "ATGC",
    warnings: [],
  }
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

  it("persists reference-frame domains separately from accession domains", () => {
    store.state.domains = [{ name: "Acc", id: "IPR1", start: 10, end: 20, db: "InterPro" }];
    store.state.refDomains = [{ name: "Ref", id: "IPR1", start: 15, end: 25, db: "PFAM" }];
    store.state.refDomainHash = "abc123";

    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3;

    expect(snap.settings.domains?.[0]?.start).toBe(10);
    expect(snap.settings.refDomains?.[0]?.start).toBe(15);
    expect(snap.settings.refDomainHash).toBe("abc123");
  });

  it("round-trips disabled diversity and liquid-handler settings", async () => {
    Object.assign(store.state, {
      domainDiversityEnabled: false,
      paretoDiversityEnabled: false,
      structuralDiversityEnabled: true,
      structureAccession: "8abc",
      structureLoaded: true,
      echoTransferVol: 250,
      echoQuadrant: "B2",
      echoUsedQuadrants: ["A1", "B2"],
      janusTransferVol: 1.5,
    });

    const snapshot = store.slice.getWorkspaceSnapshot() as WorkspaceV3;
    expect(snapshot.settings).toMatchObject({
      domainDiversityEnabled: false,
      paretoDiversityEnabled: false,
      structuralDiversityEnabled: true,
      structureAccession: "8abc",
      structureLoaded: true,
      echoTransferVol: 250,
      echoQuadrant: "B2",
      echoUsedQuadrants: ["A1", "B2"],
      janusTransferVol: 1.5,
    });

    await store.slice.restoreWorkspace(snapshot);

    expect(store.state).toMatchObject({
      domainDiversityEnabled: false,
      paretoDiversityEnabled: false,
      structuralDiversityEnabled: true,
      structureAccession: "8abc",
      structureLoaded: true,
      echoTransferVol: 250,
      echoQuadrant: "B2",
      echoUsedQuadrants: ["A1", "B2"],
      janusTransferVol: 1.5,
    });
  });

  it("restores the creation defaults for absent EVOLVEpro mode and round", async () => {
    const snapshot = store.slice.getWorkspaceSnapshot() as WorkspaceV3;
    delete snapshot.settings.evolveproMode;
    delete snapshot.settings.pipelineMode;
    delete snapshot.settings.evolveproRound;

    await store.slice.restoreWorkspace(snapshot);

    expect(store.state.evolveproMode).toBe("topN");
    expect(store.state.evolveproRound).toBe(0);
  });

  it("getWorkspaceSnapshot preserves rescue stage details for re-export", () => {
    store.state.rescuedMutationDetails = [
      {
        original: "V5F",
        rescued_by: "K53N",
        type: "auto_suggestion_l2",
        stage: 2,
      },
    ]
    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3
    expect(snap.results.rescuedMutationDetails).toEqual(store.state.rescuedMutationDetails)
  })

  it("restoreWorkspace rebuilds plate state from all design results", async () => {
    const designResults = [
      primer("M1A", 1, "SHARED"),
      primer("M2A", 2, "SHARED"),
      primer("M3A", 3, "GCAT3"),
    ]
    const staleMappings: PlateMapping[] = [
      { well: "A1", primer_name: "M1A_F", sequence: "ATGC1", primer_type: "forward", mutation: "M1A" },
      { well: "A2", primer_name: "M2A_F", sequence: "ATGC2", primer_type: "forward", mutation: "M2A" },
    ]
    const workspace: WorkspaceV3 = {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: "",
        mutationInputMode: "evolvepro",
        mutationText: "",
        evolveproCsvPath: "",
        selectedGene: "",
      },
      settings: {
        codonStrategy: "closest",
        maxPrimers: 95,
        tmFwdTarget: 62,
        tmRevTarget: 58,
        tmOverlapTarget: 42,
        gcMin: 40,
        gcMax: 60,
        autoRedesignOnLoad: false,
      },
      results: {
        designResults,
        excludedDesignMutations: ["M2A", "STALE"],
        successCount: 3,
        totalCount: 3,
        failedMutations: [],
        plateMappings: staleMappings,
        dedupInfo: {},
        manuallySwapped: {},
        customCandidates: {},
      },
      ui: { tableSorting: [] },
    }

    await store.slice.restoreWorkspace(workspace)

    // excludedDesignMutations from legacy workspace is ignored (feature removed)
    // All design results are included; plate state rebuilt from all 3 results
    // M1A and M2A share reverse seq "SHARED" — M1A is the representative reverse mutation
    expect((store.state.plateMappings as PlateMapping[]).map((mapping) => mapping.mutation)).toEqual([
      "M1A",
      "M2A",
      "M3A",
      "M1A",
      "M3A",
    ])
    expect(store.state.dedupInfo).toEqual({
      SHARED: ["M1A", "M2A"],
      GCAT3: ["M3A"],
    })
    expect(store.state.currentMajor).toBe("output")
    expect(store.state.currentSubStep).toBe("output.summary")
  })

  it("restoreWorkspace refuses the design outcome group when a count did not survive the file", async () => {
    // designResults/successCount/totalCount 는 저장 측이 한 리터럴로 함께 쓴다.
    // JSON.stringify 는 NaN/Infinity 를 null 로 쓰므로 카운트 하나가 null 로 돌아온다.
    // 표만 복원하고 카운트를 `?? 0` 으로 채우면 세 줄짜리 표 위에 "3/0" 이 뜬다.
    const designResults = [primer("M1A", 1), primer("M2A", 2), primer("M3A", 3)]
    const workspace = {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: "",
        mutationInputMode: "evolvepro",
        mutationText: "",
        evolveproCsvPath: "",
        selectedGene: "",
      },
      settings: {
        codonStrategy: "closest",
        maxPrimers: 95,
        tmFwdTarget: 62,
        tmRevTarget: 58,
        tmOverlapTarget: 42,
        gcMin: 40,
        gcMax: 60,
        autoRedesignOnLoad: false,
      },
      results: {
        designResults,
        successCount: 3,
        totalCount: null,
        failedMutations: [],
        plateMappings: [],
        dedupInfo: {},
        manuallySwapped: {},
        customCandidates: {},
      },
      ui: { tableSorting: [] },
    } as unknown as WorkspaceV3

    await store.slice.restoreWorkspace(workspace)

    // 통째로 버린다. 표만 살아 있는 부분 복원이 이 판정이 막으려는 상태다.
    expect(store.state.designResults).toEqual([])
    expect(store.state.successCount).toBe(0)
    expect(store.state.totalCount).toBe(0)
    expect(store.state.currentMajor).not.toBe("output")
    // 파일은 열리고, 무엇이 빠졌는지는 statusMessage 로 드러난다.
    expect(store.state.statusMessage).toContain("totalCount")
    // maxPrimers 의 clamp 는 그대로다. 범위를 벗어난 설정을 고치는 것과
    // 없는 측정값을 만들어 내는 것은 다른 판단이고, 이 테스트가 그 경계를 잡는다.
    expect(store.state.maxPrimers).toBe(95)
  })

  it("restoreWorkspace keeps the refusal notice through the auto re-design the refusal itself triggers", async () => {
    // 그룹을 거절하면 designResults 가 비고, 바로 그 순간 자동 재설계 조건
    // (designResults.length === 0)이 성립한다. designPrimers 는 statusMessage 를
    // 통째로 덮어쓰므로(designSlice.ts 의 "Designing primers..." 와 완료 문구)
    // 안내가 사용자에게 닿기 전에 지워진다. 아래 stub 이 그 덮어쓰기를 흉내 낸다.
    vi.mocked(sendRequest).mockResolvedValue({ genes: [] } as unknown as SequenceInfo)
    store.state.designPrimers = async () => {
      Object.assign(store.state, {
        statusMessage: "Design complete: 1/1",
        designResults: [primer("M1A", 1)],
      })
    }
    const workspace = {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: "/test/sequence.fa",
        mutationInputMode: "text",
        mutationText: "F89W",
        evolveproCsvPath: "",
        selectedGene: "",
      },
      settings: {
        codonStrategy: "closest",
        maxPrimers: 95,
        tmFwdTarget: 62,
        tmRevTarget: 58,
        tmOverlapTarget: 42,
        gcMin: 40,
        gcMax: 60,
        autoRedesignOnLoad: true,
      },
      results: {
        designResults: [primer("M1A", 1), primer("M2A", 2), primer("M3A", 3)],
        successCount: 3,
        totalCount: null,
        failedMutations: [],
        plateMappings: [],
        dedupInfo: {},
        manuallySwapped: {},
        customCandidates: {},
      },
      ui: { tableSorting: [] },
    } as unknown as WorkspaceV3

    await store.slice.restoreWorkspace(workspace)

    // 재설계는 실제로 돈다(그것이 이 상태의 회복 경로다).
    expect(store.state.statusMessage).toContain("Design complete: 1/1")
    // 그리고 저장된 표를 버렸다는 사실도 함께 남는다.
    expect(store.state.statusMessage).toContain("totalCount")
  })

  it("restoreWorkspace caps a saved design count to one plate", async () => {
    // A project saved before the bound existed, or one edited by hand, is the
    // case nothing else checks: this path calls `set` directly and never goes
    // through setMaxPrimers. The file must still open, with the count fixed.
    const workspace: WorkspaceV3 = {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: "",
        mutationInputMode: "evolvepro",
        mutationText: "",
        evolveproCsvPath: "",
        selectedGene: "",
      },
      settings: {
        codonStrategy: "closest",
        maxPrimers: 500,
        tmFwdTarget: 62,
        tmRevTarget: 58,
        tmOverlapTarget: 42,
        gcMin: 40,
        gcMax: 60,
        autoRedesignOnLoad: false,
      },
      results: {
        designResults: [],
        successCount: 0,
        totalCount: 0,
        failedMutations: [],
        plateMappings: [],
        dedupInfo: {},
        manuallySwapped: {},
        customCandidates: {},
      },
      ui: { tableSorting: [] },
    }

    await store.slice.restoreWorkspace(workspace)

    expect(store.state.maxPrimers).toBe(MAX_MUTATIONS_PER_RUN)
    expect(MAX_MUTATIONS_PER_RUN).toBe(96)
  })

  it("restoreWorkspace keeps a saved design count that already fits a plate", async () => {
    const workspace: WorkspaceV3 = {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: "",
        mutationInputMode: "evolvepro",
        mutationText: "",
        evolveproCsvPath: "",
        selectedGene: "",
      },
      settings: {
        codonStrategy: "closest",
        maxPrimers: 40,
        tmFwdTarget: 62,
        tmRevTarget: 58,
        tmOverlapTarget: 42,
        gcMin: 40,
        gcMax: 60,
        autoRedesignOnLoad: false,
      },
      results: {
        designResults: [],
        successCount: 0,
        totalCount: 0,
        failedMutations: [],
        plateMappings: [],
        dedupInfo: {},
        manuallySwapped: {},
        customCandidates: {},
      },
      ui: { tableSorting: [] },
    }

    await store.slice.restoreWorkspace(workspace)

    expect(store.state.maxPrimers).toBe(40)
  })

  it("restoreWorkspace remaps a retired Benchling selection to KOD and keeps its GC range", async () => {
    // "Benchling" (GC 30-70) was removed as a profile in v0.13.20. Re-applying
    // the replacement profile defaults here would silently rewrite an old run
    // to KOD 40-60, so the saved GC window must survive the remap.
    const workspace: WorkspaceV3 = {
      schema_version: "0.3",
      rounds: [],
      active_round_id: null,
      inputs: {
        fastaPath: "",
        mutationInputMode: "evolvepro",
        mutationText: "",
        evolveproCsvPath: "",
        selectedGene: "",
      },
      settings: {
        selectedPolymerase: "Benchling",
        codonStrategy: "closest",
        maxPrimers: 95,
        tmFwdTarget: 62,
        tmRevTarget: 58,
        tmOverlapTarget: 42,
        gcMin: 30,
        gcMax: 70,
        autoRedesignOnLoad: false,
      },
      results: {
        designResults: [],
        successCount: 0,
        totalCount: 0,
        failedMutations: [],
        plateMappings: [],
        dedupInfo: {},
        manuallySwapped: {},
        customCandidates: {},
      },
      ui: { tableSorting: [] },
    }

    await store.slice.restoreWorkspace(workspace)

    expect(store.state.selectedPolymerase).toBe("KOD")
    expect(store.state.gcMin).toBe(30)
    expect(store.state.gcMax).toBe(70)
    expect(store.state.statusMessage).toContain("Benchling")
    expect(store.state.statusMessage).toContain("30-70%")
  })

  it("restoreWorkspace rejects schema_version < 0.3 (v2)", async () => {
    const oldWorkspace = {
      version: 2 as const,
      inputs: { fastaPath: "", mutationInputMode: "text" as const, mutationText: "", evolveproCsvPath: "", selectedGene: "" },
      settings: { codonStrategy: "closest" as const, maxPrimers: 95, tmFwdTarget: 62, tmRevTarget: 58, tmOverlapTarget: 42, gcMin: 40, gcMax: 60 },
      results: { designResults: [], successCount: 0, totalCount: 0, failedMutations: [], plateMappings: [], dedupInfo: {}, manuallySwapped: {}, customCandidates: {} },
      ui: { tableSorting: [] },
    }
    await expect(store.slice.restoreWorkspace(oldWorkspace)).rejects.toThrow(/older than v0\.3/i)
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
    await expect(store.slice.restoreWorkspace(oldWorkspace)).rejects.toThrow(/older than v0\.3/i)
  })

  it("resetAll clears EVOLVEpro ranked candidates, selected variants, and extra-exposed count", () => {
    store.state.evolveproRankedCandidates = [
      { variant: "F89W", y_pred: 0.9, aa_position: 89 },
    ]
    store.state.evolveproSelectedVariants = ["F89W"]
    store.state.evolveproExtraExposed = 25

    store.slice.resetAll({ preserveWorkspaceArtifacts: true })

    expect(store.state.evolveproRankedCandidates).toEqual([])
    expect(store.state.evolveproSelectedVariants).toEqual([])
    expect(store.state.evolveproExtraExposed).toBe(10)
  })

  it("rejects Excel export failure so the UI cannot toast that it was saved", async () => {
    vi.mocked(sendRequest).mockRejectedValueOnce(new Error("disk full"))
    await expect(store.slice.exportExcel("/test/output.xlsx")).rejects.toThrow("disk full")
    expect(store.state.statusMessage).toMatch(/Excel export failed/)
  })

  it("leaves a missing restored EVOLVEpro prediction absent instead of fabricating 0.0", async () => {
    vi.mocked(sendRequest).mockResolvedValueOnce({
      variants: ["A1V", "B2C"],
      y_preds: [0.8],
      pool_variants: [],
    } as never)
    await store.slice.restoreWorkspace({
      schema_version: "0.3",
      rounds: [], active_round_id: null,
      inputs: { fastaPath: "", mutationInputMode: "evolvepro", mutationText: "", evolveproCsvPath: "/test/evolve.csv", selectedGene: "" },
      settings: { codonStrategy: "closest", maxPrimers: 95, tmFwdTarget: 62, tmRevTarget: 58, tmOverlapTarget: 42, gcMin: 40, gcMax: 60 },
      results: { designResults: [], successCount: 0, totalCount: 0, failedMutations: [], plateMappings: [], dedupInfo: {}, manuallySwapped: {}, customCandidates: {} },
      ui: { tableSorting: [] },
    } as WorkspaceV3)
    expect(store.state.yPredMap).toEqual({ A1V: 0.8 })
    expect(store.state.yPredMap).not.toHaveProperty("B2C")
  })

  it("getWorkspaceSnapshot still includes kuro inputs (backward compat)", () => {
    const snap = store.slice.getWorkspaceSnapshot() as WorkspaceV3
    expect(snap.inputs).toBeDefined()
    expect(snap.inputs.fastaPath).toBe("/test/sequence.fa")
  })
})
