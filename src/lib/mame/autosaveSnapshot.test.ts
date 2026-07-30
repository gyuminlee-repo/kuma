import { describe, expect, it } from "vitest";
import { BUILD_EVOLVEPRO_DEFAULT_STATE, createBuildEvolveproCompletion } from "@/lib/mame/buildEvolveproFormStorage";
import type { DistributionStats, ReplicateResult, RunHealthData, VerdictRecord, WellEntry } from "@/types/mame/models";
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
    });

    expect(snapshot).toMatchObject({
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
