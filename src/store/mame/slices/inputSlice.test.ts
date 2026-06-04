import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createInputSlice } from "./inputSlice";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = {
    setVerdicts: vi.fn(),
    setReplicates: vi.fn(),
    setSummary: vi.fn(),
    setOutputPath: vi.fn((outputPath: string) => {
      state.outputPath = outputPath;
    }),
    setDistributionStats: vi.fn(),
    loadPlateData: vi.fn().mockResolvedValue(undefined),
    loadRunHealth: vi.fn().mockResolvedValue(undefined),
    ...initial,
  };

  const set = (
    updater:
      | Partial<AppState>
      | ((current: AppState) => Partial<AppState>),
  ) => {
    const updates =
      typeof updater === "function"
        ? updater(state as AppState)
        : updater;
    Object.assign(state, updates);
  };
  const get = () => state as AppState;
  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  );
  Object.assign(state, slice, initial);
  return state as AppState;
}

const distributionStats = {
  n_files: 0,
  file_size_kb: {
    min: 0,
    p05: 0,
    p25: 0,
    median: 0,
    p75: 0,
    p95: 0,
    max: 0,
    mean: 0,
    std: 0,
  },
  suggested_cutoff_kb: 50,
  suggested_method: "fixed_50" as const,
  bimodal: false,
};

describe("mame inputSlice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("defaults new analyses to raw MinKNOW run folders", () => {
    const store = makeStore();
    expect(store.inputMode).toBe("raw_run");
  });

  it("runs combinatorial demux from a raw MinKNOW run before calling analyze", async () => {
    const store = makeStore({
      inputDir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "raw_run",
      rawRunParams: {
        ...makeStore().rawRunParams,
        customBarcodesPath: "D:/project/barcodes sequence.xlsx",
      },
      cdsEnd: 900,
    });

    const demuxOutputDir = "D:/project/demux_filtered";
    // Detect runs FIRST now (call #1). total_count: 1 keeps the single-pool
    // linear path: detect -> demux -> analyze.
    mockSendRequest
      .mockResolvedValueOnce({
        fastq_pass: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e/fastq_pass",
        min_share: 0.05,
        native_barcodes: [
          {
            name: "barcode06",
            sort_barcode_name: "sort_barcode06",
            fastq_bytes: 1_000_000,
            fastq_mb: 1.0,
            share: 1.0,
            is_used: true,
          },
        ],
        used_count: 1,
        total_count: 1,
      })
      .mockResolvedValueOnce({
        output_dir: demuxOutputDir,
        stats: {
          total_reads: 10,
          passed_mapq: 10,
          passed_coverage: 9,
          assigned_reads: 8,
          ambiguous_dropped: 1,
          chimera_splits: 0,
          wells_with_reads: 2,
          wells_with_min_reads: 2,
        },
        wells_with_reads: 2,
        assigned_reads: 8,
        chimera_splits: 0,
        per_well_consensus: {},
        per_well_read_counts: { "1_1": 5, "1_2": 3 },
      })
      .mockResolvedValueOnce({
        verdicts: [],
        replicates: [],
        output_path: "D:/project/mame_result.xlsx",
        summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
        distribution_stats: distributionStats,
      });

    await store.runAnalysis();

    expect(mockSendRequest).toHaveBeenNthCalledWith(
      1,
      "mame.detect_native_barcodes",
      expect.objectContaining({
        minknow_run_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      }),
    );
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      2,
      "mame.run_combinatorial_demux",
      expect.objectContaining({
        minknow_run_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
        custom_barcodes_xlsx: "D:/project/barcodes sequence.xlsx",
        reference_fasta: "D:/project/ref.fasta",
        output_dir: demuxOutputDir,
        coverage_fraction: 0.98,
        edit_dist_ratio: 0.25,
        chimera_split: true,
        native_barcodes: null,
      }),
      1_800_000,
    );
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      3,
      "analyze",
      expect.objectContaining({
        input_dir: demuxOutputDir,
        ingest_mode: "barcode",
      }),
      1_200_000,
    );
    expect(store.isAnalyzing).toBe(false);
    expect(store.analyzeMessage).toBe("Analysis complete");
  });

  it("does not call analyze when raw mode lacks a custom barcode file", async () => {
    const store = makeStore({
      inputDir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "raw_run",
      cdsEnd: 900,
    });

    await store.runAnalysis();

    expect(mockSendRequest).not.toHaveBeenCalled();
    expect(store.isAnalyzing).toBe(false);
    expect(store.validationErrors).toEqual([
      "Custom Barcodes (.xlsx or .csv) file is required.",
    ]);
  });

  it("pauses for per-NB selection when detect finds multiple native barcodes", async () => {
    const store = makeStore({
      inputDir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "raw_run",
      rawRunParams: {
        ...makeStore().rawRunParams,
        customBarcodesPath: "D:/project/barcodes sequence.xlsx",
      },
      cdsEnd: 900,
    });

    const nativeBarcodes = [
      {
        name: "barcode06",
        sort_barcode_name: "sort_barcode06",
        fastq_bytes: 6_000_000,
        fastq_mb: 6.0,
        share: 0.6,
        is_used: true,
      },
      {
        name: "barcode20",
        sort_barcode_name: "sort_barcode20",
        fastq_bytes: 4_000_000,
        fastq_mb: 4.0,
        share: 0.4,
        is_used: true,
      },
    ];

    // Detect returns total_count: 2 -> dialog opens, no demux/analyze yet.
    mockSendRequest.mockResolvedValueOnce({
      fastq_pass: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e/fastq_pass",
      min_share: 0.05,
      native_barcodes: nativeBarcodes,
      used_count: 2,
      total_count: 2,
    });

    await store.runAnalysis();

    // Only detect fired; demux/analyze deferred to the confirm action.
    expect(mockSendRequest).toHaveBeenCalledTimes(1);
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      1,
      "mame.detect_native_barcodes",
      expect.objectContaining({
        minknow_run_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      }),
    );
    expect(store.detectedNativeBarcodes).toHaveLength(2);
    expect(store.isDetectingBarcodes).toBe(false);
    expect(store.isAnalyzing).toBe(true);

    // Confirm with the user-selected native barcodes -> demux (native_barcodes
    // threaded) then analyze.
    mockSendRequest
      .mockResolvedValueOnce({
        output_dir: "D:/project/demux_filtered",
        stats: {
          total_reads: 10,
          passed_mapq: 10,
          passed_coverage: 9,
          assigned_reads: 8,
          ambiguous_dropped: 1,
          chimera_splits: 0,
          wells_with_reads: 2,
          wells_with_min_reads: 2,
        },
        wells_with_reads: 2,
        assigned_reads: 8,
        chimera_splits: 0,
        per_well_consensus: {},
        per_well_read_counts: { "1_1": 5, "1_2": 3 },
      })
      .mockResolvedValueOnce({
        verdicts: [],
        replicates: [],
        output_path: "D:/project/mame_result.xlsx",
        summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
        distribution_stats: distributionStats,
      });

    await store.confirmNativeBarcodeSelection(["barcode06", "barcode20"]);

    expect(store.detectedNativeBarcodes).toBeNull();
    // Calls now: 1 detect (above) + 2 demux + 3 analyze.
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      2,
      "mame.run_combinatorial_demux",
      expect.objectContaining({
        native_barcodes: ["barcode06", "barcode20"],
        output_dir: "D:/project/demux_filtered",
      }),
      1_800_000,
    );
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      3,
      "analyze",
      expect.objectContaining({
        input_dir: "D:/project/demux_filtered",
        ingest_mode: "barcode",
      }),
      1_200_000,
    );
    expect(store.isAnalyzing).toBe(false);
    expect(store.analyzeMessage).toBe("Analysis complete");
  });
});
