import { describe, expect, it } from "vitest";
import { BUILD_EVOLVEPRO_DEFAULT_STATE, createBuildEvolveproCompletion } from "@/lib/mame/buildEvolveproFormStorage";
import type { DistributionStats, ReplicateResult, RunHealthData, VerdictRecord, WellEntry } from "@/types/mame/models";
import type { Round } from "@/types/round";
import { buildMameSnapshot } from "./autosaveSnapshot";

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
        layoutXlsx: "/proj/layout.xlsx",
        gcDataXlsx: "/proj/gc.xlsx",
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

// ─── schema 4: 이식 가능한 경로 ──────────────────────────────────────────

describe("buildMameSnapshot path portability", () => {
  /** 경로 필드만 있으면 되는 최소 상태. 나머지는 빌더가 그대로 통과시킨다. */
  function stateWith(paths: {
    inputDir: string;
    expectedPath: string;
    referencePath: string;
    outputPath: string;
    sampleMapPath: string;
  }) {
    return {
      ...paths,
      mode: "amplicon",
      ingestMode: "barcode",
      inputMode: "raw_run",
      rawRunParams: {},
      cdsStart: 0,
      cdsEnd: 0,
      minFileSizeKb: 50,
      manyCutoff: 5,
    } as unknown as Parameters<typeof buildMameSnapshot>[0];
  }

  it("writes in-project inputs as relative and outside ones as external", () => {
    const snap = buildMameSnapshot(
      stateWith({
        inputDir: "/data/20260212_1430_MN",
        expectedPath: "/proj/inputs/expected.xlsx",
        referencePath: "/proj/inputs/ref.fasta",
        outputPath: "/proj/out/mame_result.xlsx",
        sampleMapPath: "",
      }),
      undefined,
      "/proj",
    );

    expect(snap.input.expected_path).toEqual({
      kind: "project",
      rel: "inputs/expected.xlsx",
    });
    expect(snap.input.output_path).toEqual({
      kind: "project",
      rel: "out/mame_result.xlsx",
    });
    // The raw run folder is gigabytes and lives outside the project, so it is
    // recorded as a reference to re-point rather than something to carry along.
    expect(snap.input.input_dir).toEqual({
      kind: "external",
      path: "/data/20260212_1430_MN",
      name: "20260212_1430_MN",
    });
    // Empty stays empty: wrapping it would make "not set" indistinguishable.
    expect(snap.input.sample_map_path).toBe("");
  });

  it("keeps every path external when there is no project", () => {
    const snap = buildMameSnapshot(
      stateWith({
        inputDir: "/data/run",
        expectedPath: "/proj/inputs/expected.xlsx",
        referencePath: "",
        outputPath: "",
        sampleMapPath: "",
      }),
      undefined,
      null,
    );

    expect(snap.input.expected_path).toMatchObject({ kind: "external" });
  });

  it("declares schema 4 so older builds refuse the new shape instead of misreading it", () => {
    const snap = buildMameSnapshot(
      stateWith({
        inputDir: "",
        expectedPath: "",
        referencePath: "",
        outputPath: "",
        sampleMapPath: "",
      }),
      undefined,
      "/proj",
    );
    expect(snap.schema).toBe(4);
  });
});
