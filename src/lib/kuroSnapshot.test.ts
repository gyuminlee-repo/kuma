import { describe, expect, it } from "vitest";
import { buildKuroSnapshot, KURO_SCHEMA, type KuroSnapshotState } from "./kuroSnapshot";

const baseState: KuroSnapshotState = {
  fastaPath: "/project/input.gb",
  selectedGene: "42",
  organism: "ecoli",
  seqInfo: null,
  mutationText: "A1V",
  mutationInputMode: "evolvepro",
  evolveproCsvPath: "/project/evolvepro.csv",
  evolveproMode: "pipeline",
  evolveproVariantColumn: "variant",
  evolveproScoreColumn: "score",
  evolveproScoreOrder: "asc",
  evolveproSheetName: "Sheet1",
  uniprotAccession: "P42212",
  domains: [],
  disabledDomains: [],
  positionDiversityEnabled: true,
  maxPerPosition: 2,
  domainDiversityEnabled: true,
  domainStrategy: "equal",
  domainOverlapPolicy: "largest",
  linkerHandling: "exclude",
  domainQuotaMin: 3,
  paretoDiversityEnabled: true,
  entropyWeightEnabled: true,
  entropyWeight: 0.4,
  paretoPoolMultiplier: 2,
  distanceMode: "3d",
  structuralDiversityEnabled: false,
  structuralKappa: 0.3,
  refDomains: [],
  refDomainHash: "",
  structureAccession: "",
  structureLoaded: false,
  uniprotCandidates: [],
  evolveproRound: 2,
  roundSize: 96,
  autoRedesignOnLoad: false,
  saveCache: false,
  selectedPolymerase: "Benchling",
  codonStrategy: "optimal",
  maxPrimers: 48,
  tmFwdTarget: 62,
  tmRevTarget: 58,
  tmOverlapTarget: 42,
  gcMin: 40,
  gcMax: 60,
  primerLenEnabled: true,
  fwdLenMin: 18,
  fwdLenMax: 34,
  revLenMin: 19,
  revLenMax: 28,
  fillOnFailure: true,
  overlapMode: "full",
  tmTolerance: 4.0,
  randomSeed: null,
  echoTransferVol: 100,
  echoQuadrant: null,
  echoUsedQuadrants: [],
  janusTransferVol: 2,
  benchmarkTopPercentile: 10,
  benchmarkRandomTrials: 100,
  benchmarkRandomSeed: null,
  designResults: [],
  successCount: 0,
  totalCount: 0,
  failedMutations: [],
  plateMappings: [],
  dedupInfo: {},
  manuallySwapped: {},
  customCandidates: {},
  rescuedMutationDetails: [],
  poolVariants: [],
  rescuedMutations: [],
  alternativesCache: {},
  benchmarkResults: null,
  showBenchmark: false,
  tableSorting: [],
  currentMajor: "design",
  currentSubStep: "design.load",
  stepStatus: {
    "design.load": { done: false, reachable: true },
    "design.mutation": { done: false, reachable: true },
    "design.params": { done: false, reachable: true },
    "design.submit": { done: false, reachable: true },
    "output.summary": { done: false, reachable: true },
    "export.all": { done: false, reachable: true },
  },
  yPredMap: {},
  evolveproSelectedVariants: [],
  evolveproExtraExposed: 10,
  evolveproRankedCandidates: [],
  evolveproUsedVariantColumn: null,
  evolveproUsedScoreColumn: null,
  evolveproTotalCount: 0,
  evolveproFilteredCount: null,
  evolveproParetoExchanges: null,
  evolveproStepStats: null,
  domainStats: {},
};

describe("buildKuroSnapshot: schema 6", () => {
  it("uses schema 6", () => {
    expect(KURO_SCHEMA).toBe(6);
    expect(buildKuroSnapshot(baseState).schema).toBe(6);
  });

  it("serializes navigation, pipeline, ui, benchmark and sequence_info blocks", () => {
    const snapshot = buildKuroSnapshot({
      ...baseState,
      currentMajor: "output",
      currentSubStep: "output.summary",
      tableSorting: [{ id: "mutation", desc: false }],
      yPredMap: { A1B: 0.5 },
      evolveproSelectedVariants: ["A1B"],
      seqInfo: { header: "h", seq_length: 3, genes: [] } as unknown as KuroSnapshotState["seqInfo"],
    });

    expect(snapshot.navigation).toMatchObject({
      current_major: "output",
      current_sub_step: "output.summary",
    });
    expect(snapshot.ui).toMatchObject({ table_sorting: [{ id: "mutation", desc: false }] });
    expect(snapshot.pipeline).toMatchObject({
      y_pred_map: { A1B: 0.5 },
      evolvepro_selected_variants: ["A1B"],
    });
    expect(snapshot.benchmark).toMatchObject({
      benchmark_top_percentile: 10,
      benchmark_random_trials: 100,
    });
    expect(snapshot.input).toMatchObject({
      sequence_info: { header: "h", seq_length: 3, genes: [] },
    });
  });

  it("includes source fingerprints from extras", () => {
    const snapshot = buildKuroSnapshot(baseState, null, {
      sequenceFingerprint: { size: 10, mtimeMs: 123 },
      evolveproCsvFingerprint: null,
    });

    expect(snapshot.sources).toMatchObject({
      sequence_fingerprint: { size: 10, mtimeMs: 123 },
      evolvepro_csv_fingerprint: null,
    });
  });

  it("does not store rounds/active_round_id (MAME 스냅샷 단독 소유)", () => {
    const snapshot = buildKuroSnapshot(baseState);

    expect(snapshot).not.toHaveProperty("rounds");
    expect(snapshot).not.toHaveProperty("active_round_id");
  });

  it("gates alternativesCache/benchmarkResults behind saveCache", () => {
    const withCache = buildKuroSnapshot({
      ...baseState,
      saveCache: true,
      alternativesCache: { A1B: [] },
    });
    const withoutCache = buildKuroSnapshot({
      ...baseState,
      saveCache: false,
      alternativesCache: { A1B: [] },
    });

    expect((withCache.results as Record<string, unknown>).alternativesCache).toEqual({ A1B: [] });
    expect((withoutCache.results as Record<string, unknown>).alternativesCache).toBeUndefined();
  });
});

describe("buildKuroSnapshot: schema 4 poolVariants", () => {
  it("uses schema 6 (schema 4 필드는 그대로 유지)", () => {
    expect(buildKuroSnapshot(baseState).schema).toBe(6);
  });

  it("includes poolVariants in the results block", () => {
    const snapshot = buildKuroSnapshot({
      ...baseState,
      designResults: [],
      poolVariants: ["A1B", "P50Q"],
    });
    expect(snapshot.results).toMatchObject({
      poolVariants: ["A1B", "P50Q"],
    });
  });
});

describe("buildKuroSnapshot", () => {
  it("serializes autosave inputs needed to restore EVOLVEpro mode with column overrides", () => {
    const snapshot = buildKuroSnapshot(baseState);

    expect(snapshot.input).toMatchObject({
      sequence_path: "/project/input.gb",
      selected_cds: "42",
      mutation_input_mode: "evolvepro",
      evolvepro_mode: "pipeline",
      evolvepro_csv_path: "/project/evolvepro.csv",
      evolvepro_variant_column: "variant",
      evolvepro_score_column: "score",
      evolvepro_score_order: "asc",
      evolvepro_sheet_name: "Sheet1",
      uniprot_accession: "P42212",
      organism: "ecoli",
    });
  });

  it("serializes parameters and diversity settings that hydration reapplies", () => {
    const snapshot = buildKuroSnapshot(baseState);

    expect(snapshot.parameters).toMatchObject({
      codon_strategy: "optimal",
      overlap_mode: "full",
    });
    expect(snapshot.diversity).toMatchObject({
      domain_strategy: "equal",
      domain_overlap_policy: "largest",
      linker_handling: "exclude",
      domain_quota_min: 3,
      distance_mode: "3d",
      auto_redesign_on_load: false,
      save_cache: false,
    });
  });

  it("serializes structural diversity settings", () => {
    const snapshot = buildKuroSnapshot(baseState);
    expect(snapshot.diversity).toMatchObject({
      structural_diversity_enabled: false,
      structural_kappa: 0.3,
    });
  });

  it("serializes structural diversity enabled=true with custom kappa", () => {
    const snapshot = buildKuroSnapshot({
      ...baseState,
      structuralDiversityEnabled: true,
      structuralKappa: 0.7,
    });
    expect(snapshot.diversity).toMatchObject({
      structural_diversity_enabled: true,
      structural_kappa: 0.7,
    });
  });

  it("serializes liquid-handler controls and picker exposure", () => {
    const snapshot = buildKuroSnapshot({
      ...baseState,
      echoTransferVol: 250,
      echoQuadrant: "B2",
      echoUsedQuadrants: ["A1", "B2"],
      janusTransferVol: 1.5,
      evolveproExtraExposed: 24,
    });

    expect(snapshot.parameters).toMatchObject({
      echo_transfer_vol: 250,
      echo_quadrant: "B2",
      echo_used_quadrants: ["A1", "B2"],
      janus_transfer_vol: 1.5,
    });
    expect(snapshot.pipeline).toMatchObject({ evolvepro_extra_exposed: 24 });
  });
});

describe("buildKuroSnapshot 경로 이식성", () => {
  it("프로젝트 폴더 안 경로를 project:// 상대 경로로 저장한다", () => {
    const snapshot = buildKuroSnapshot(baseState, "/project");

    expect(snapshot.input).toMatchObject({
      sequence_path: "project://input.gb",
      evolvepro_csv_path: "project://evolvepro.csv",
    });
  });

  it("프로젝트 폴더 밖 경로는 절대 경로로 남긴다", () => {
    const snapshot = buildKuroSnapshot(
      { ...baseState, fastaPath: "/elsewhere/ref.gb" },
      "/project",
    );

    expect(snapshot.input).toMatchObject({
      sequence_path: "/elsewhere/ref.gb",
      evolvepro_csv_path: "project://evolvepro.csv",
    });
  });

  it("projectPath를 주지 않으면 절대 경로를 그대로 둔다 (scratch 세션)", () => {
    const snapshot = buildKuroSnapshot(baseState);

    expect(snapshot.input).toMatchObject({
      sequence_path: "/project/input.gb",
      evolvepro_csv_path: "/project/evolvepro.csv",
    });
  });

  it("빈 경로는 null로 유지한다", () => {
    const snapshot = buildKuroSnapshot(
      { ...baseState, fastaPath: "", evolveproCsvPath: "" },
      "/project",
    );

    expect(snapshot.input).toMatchObject({
      sequence_path: null,
      evolvepro_csv_path: null,
    });
  });
});
