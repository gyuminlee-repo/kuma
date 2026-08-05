import { describe, expect, it } from "vitest";
import { BUILD_EVOLVEPRO_DEFAULT_STATE, createBuildEvolveproCompletion } from "@/lib/mame/buildEvolveproFormStorage";
import type { DistributionStats, ReplicateResult, RunHealthData, VerdictRecord, WellEntry } from "@/types/mame/models";
import type { Round } from "@/types/round";
import { buildMameSnapshot, type MameSnapshotState } from "./autosaveSnapshot";

const verdict: VerdictRecord = {
  native_barcode: "barcode1",
  custom_barcode: "1_1",
  file_size_kb: 120,
  read_count: 160,
  n_mixed_positions: 0,
  max_minor_allele_fraction: 0,
  n_low_depth_positions: 0,
  consensus_n_fraction: 0,
  n_low_quality_bases: 0,
  n_input_reads: 160,
  n_aligned_reads: 155,
  n_mapq_failed: 0,
  n_span_failed: 0,
  source_path: "/mock/NB01/1_1.fasta",
  aa_sequence: "MSTTS",
  observed_nt_changes: [],
  n_no_call_aa: 0,
  observed_aa_changes: ["V5F"],
  expected_mutations: ["V5F"],
  mutant_id: "V5F",
  verdict: "PASS",
  verdict_notes: "",
};

const replicate: ReplicateResult = {
  mutant_id: "V5F",
  selected_plate: "barcode1",
  selection_reason: "only_pass",
  failed: false,
  plate_keys: ["barcode1"],
  plate_verdicts: { barcode1: verdict },
  is_fallback: false,
  fallback_reason: null,
};

const distributionStats: DistributionStats = {
  n_files: 1,
  file_size_kb: { min: 120, p05: 120, p25: 120, median: 120, p75: 120, p95: 120, max: 120, mean: 120, std: 0 },
  suggested_cutoff_kb: 50,
  suggested_method: "fixed_50",
  bimodal: false,
};

const well: WellEntry = {
  well: "A01",
  barcode: "1_1",
  native_barcode: "barcode1",
  verdict: "PASS",
  mutant_id: "V5F",
  selected: true,
  notes: "",
  is_fallback: false,
  fallback_reason: null,
};

const runHealth: RunHealthData = {
  per_plate_summary: {},
  file_size_distribution: {},
  suggested_cutoff_kb: 50,
  bimodal: false,
  suggested_method: "fixed_50",
  pore_yield_pct: null,
  throughput_timeline: null,
  barcode_distribution: null,
  cross_talk_candidates: [],
  recovered_mutants: null,
  total_mutants: 1,
  recovery_rate: 1,
};

const round: Round = {
  id: "round_1",
  n: 1,
  created_at: "2026-07-30T00:00:00.000Z",
  status: "activity_linked",
  error_info: null,
  plate_meta: { plates: [{ plate_id: "plate01", wt_wells: ["A01"], control_wells: [] }] },
  design: {},
  genotype: {},
  activity: {
    records: [
      {
        plate_id: "plate01",
        well_id: "A01",
        value: 2.4,
        replicate_idx: 1,
        is_wt: false,
        source_file: "/proj/activity.csv",
      },
    ],
    plate_meta: { plates: [{ plate_id: "plate01", wt_wells: ["A01"], control_wells: [] }] },
  },
  merged_table: [
    {
      plate_id: "plate01",
      well_id: "A01",
      mutation: "V5F",
      mutation_source: "mame_genotype",
      expected_mutation: "V5F",
      called_mutation: "V5F",
      ngs_success: true,
      activity_raw_mean: 2.4,
      activity_raw_sd: 0,
      activity_replicates: [2.4],
      replicate_n: 1,
      fold_change: 2.3,
      log2_fc: 1.2,
    },
  ],
};

describe("buildMameSnapshot", () => {
  it("stores all user-visible result state for literal save-load", () => {
    const buildCompletion = createBuildEvolveproCompletion(
      {
        ...BUILD_EVOLVEPRO_DEFAULT_STATE,
        activityPath: "/proj/activity.csv",
        activityScale: "relative_to_wt",
        verdictXlsx: "/proj/verdict.xlsx",
        outputXlsx: "/proj/evolvepro.xlsx",
      },
      "/proj/evolvepro.xlsx",
    );

    const snapshot = buildMameSnapshot({
      inputDir: "/proj/run",
      expectedPath: "/proj/expected.xlsx",
      referencePath: "/proj/ref.fa",
      outputPath: "/proj/out",
      sampleMapPath: "/proj/sample_map.xlsx",
      mode: "amplicon",
      ingestMode: "barcode",
      inputMode: "raw_run",
      rawRunParams: {
        customBarcodesPath: "/proj/barcodes.xlsx",
        sequencingSummaryPath: "/proj/sequencing_summary.txt",
        minQscore: 10,
        lengthMin: 0,
        lengthMax: 0,
        targetLength: null,
        lengthToleranceBp: 50,
        normalizeHeaders: true,
        coverageFraction: 0.98,
        editDistRatio: 0.25,
        chimeraSplit: true,
      },
      cdsStart: 1,
      cdsEnd: 900,
      minFileSizeKb: 50,
      manyCutoff: 5,
      verdicts: [verdict],
      replicates: [replicate],
      summary: { total: 1, pass_count: 1, ambiguous_count: 0, fail_count: 0 },
      distributionStats,
      wells: [well],
      selectedWell: well,
      runHealth,
      buildEvolveproCompletion: buildCompletion,
      demuxResult: null,
      ampliconLengthEstimate: null,
      wellLayout: { A01: "V5F" },
    }, {
      rounds: [round],
      activeRoundId: "round_1",
    });

    expect(snapshot).toMatchObject({
      rounds: [round],
      active_round_id: "round_1",
      results: {
        verdicts: [verdict],
        replicates: [replicate],
        summary: { total: 1, pass_count: 1, ambiguous_count: 0, fail_count: 0 },
        distribution_stats: distributionStats,
        wells: [well],
        selected_well: well,
        run_health: runHealth,
        build_evolvepro_completion: buildCompletion,
        demux_result: null,
        amplicon_length_estimate: null,
        well_layout: { A01: "V5F" },
      },
    });
  });
});

describe("buildMameSnapshot 경로 이식성", () => {
  // 경로 필드만 보는 테스트라 나머지는 최소값으로 채운다.
  const pathState = (overrides: Partial<MameSnapshotState> = {}): MameSnapshotState => ({
    inputDir: "/proj/run",
    expectedPath: "/proj/expected.xlsx",
    referencePath: "/proj/ref.fa",
    outputPath: "/proj/out",
    sampleMapPath: "/proj/sample_map.xlsx",
    mode: "amplicon",
    ingestMode: "barcode",
    inputMode: "raw_run",
    rawRunParams: {
      customBarcodesPath: "",
      sequencingSummaryPath: "",
      minQscore: 10,
      lengthMin: 0,
      lengthMax: 0,
      targetLength: null,
      lengthToleranceBp: 50,
      normalizeHeaders: true,
      coverageFraction: 0.98,
      editDistRatio: 0.25,
      chimeraSplit: true,
    },
    cdsStart: 1,
    cdsEnd: 900,
    minFileSizeKb: 50,
    manyCutoff: 5,
    verdicts: [],
    replicates: [],
    summary: null,
    distributionStats: null,
    wells: [],
    selectedWell: null,
    runHealth: null,
    buildEvolveproCompletion: null,
    demuxResult: null,
    ampliconLengthEstimate: null,
    wellLayout: null,
    ...overrides,
  });

  it("프로젝트 폴더 안 경로를 project:// 상대 경로로 저장한다", () => {
    const snapshot = buildMameSnapshot(pathState(), undefined, "/proj");

    expect(snapshot.input).toEqual({
      input_dir: "project://run",
      expected_path: "project://expected.xlsx",
      reference_path: "project://ref.fa",
      output_path: "project://out",
      sample_map_path: "project://sample_map.xlsx",
    });
  });

  it("프로젝트 폴더 밖 raw run 폴더는 절대 경로로 남긴다", () => {
    const snapshot = buildMameSnapshot(
      pathState({ inputDir: "/ngs/run_20260730" }),
      undefined,
      "/proj",
    );

    expect(snapshot.input.input_dir).toBe("/ngs/run_20260730");
    expect(snapshot.input.reference_path).toBe("project://ref.fa");
  });

  it("projectPath를 주지 않으면 절대 경로를 그대로 둔다 (scratch 세션)", () => {
    const snapshot = buildMameSnapshot(pathState());

    expect(snapshot.input.input_dir).toBe("/proj/run");
    expect(snapshot.input.expected_path).toBe("/proj/expected.xlsx");
  });

  it("빈 경로는 빈 문자열로 유지한다", () => {
    const snapshot = buildMameSnapshot(pathState({ sampleMapPath: "" }), undefined, "/proj");

    expect(snapshot.input.sample_map_path).toBe("");
  });

  it("schema 를 4 로 올려 구 빌드가 새 스냅샷을 잘못 읽지 않게 한다", () => {
    expect(buildMameSnapshot(pathState(), undefined, "/proj").schema).toBe(4);
  });
});

// ─── raw_run_params 안의 경로 ────────────────────────────────────────────

describe("buildMameSnapshot raw run params portability", () => {
  /** 경로 두 개만 보면 되는 최소 상태. */
  function stateWithRawParams(params: Record<string, unknown>) {
    return {
      inputDir: "",
      expectedPath: "",
      referencePath: "",
      outputPath: "",
      sampleMapPath: "",
      mode: "amplicon",
      ingestMode: "barcode",
      inputMode: "raw_run",
      rawRunParams: {
        customBarcodesPath: "",
        sequencingSummaryPath: "",
        minQscore: 9,
        lengthMin: 0,
        lengthMax: 0,
        targetLength: null,
        lengthToleranceBp: 50,
        normalizeHeaders: true,
        coverageFraction: 0.98,
        editDistRatio: 0.25,
        chimeraSplit: true,
        ...params,
      },
      cdsStart: 0,
      cdsEnd: 0,
      minFileSizeKb: 50,
      manyCutoff: 5,
    } as unknown as Parameters<typeof buildMameSnapshot>[0];
  }

  it("relativises the two paths and leaves the rest of the params alone", () => {
    const snap = buildMameSnapshot(
      stateWithRawParams({
        customBarcodesPath: "/proj/inputs/barcodes.xlsx",
        sequencingSummaryPath: "/data/run/sequencing_summary.txt",
      }),
      undefined,
      "/proj",
    );

    expect(snap.parameters.raw_run_params.customBarcodesPath).toBe(
      "project://inputs/barcodes.xlsx",
    );
    // Outside the project, so it stays absolute rather than pretending it can
    // travel with the folder.
    expect(snap.parameters.raw_run_params.sequencingSummaryPath).toBe(
      "/data/run/sequencing_summary.txt",
    );
    // Thresholds are not paths and must survive untouched.
    expect(snap.parameters.raw_run_params).toMatchObject({
      minQscore: 9,
      coverageFraction: 0.98,
      chimeraSplit: true,
    });
  });

  it("leaves unset paths empty rather than turning them into a project root", () => {
    const snap = buildMameSnapshot(stateWithRawParams({}), undefined, "/proj");

    expect(snap.parameters.raw_run_params.customBarcodesPath).toBe("");
    expect(snap.parameters.raw_run_params.sequencingSummaryPath).toBe("");
  });
});
