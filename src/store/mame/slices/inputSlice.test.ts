import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createInputSlice } from "./inputSlice";
import { createAnalysisSliceDoubles } from "./testHelpers/analysisSliceDoubles";
import { useRoundStore } from "@/store/round/roundSlice";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = {
    ...createAnalysisSliceDoubles(),
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

/**
 * What the raw-run path reports about the reference it actually read: the
 * pipeline finds the barcode primer tails inside the picked file and analyses
 * the amplicon between them, so the file named in the form is not the file the
 * run read. Only this branch resolves one.
 */
const referenceResolution = {
  path: "D:/project/demux_filtered/ref.amplicon.fa",
  extracted: true,
  span_start: 451,
  span_end: 1170,
  original_length: 1620,
  cds_start: 61,
  cds_end: 660,
  note: "Amplicon extracted from reference positions 451-1170 (720 bp).",
};

describe("mame inputSlice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRoundStore.setState({ rounds: [], active_round_id: null });
  });

  it("defaults new analyses to raw MinKNOW run folders", () => {
    const store = makeStore();
    expect(store.inputMode).toBe("raw_run");
    expect(store.minFilteredDepth).toBe(30);
  });

  it("folds demux into a single analyze call from a raw MinKNOW run", async () => {
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
      cdsStart: 101,
      cdsEnd: 900,
      minFilteredDepth: 47,
      wtPlacement: "after_last_variant",
    });
    const targetRoundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });

    const demuxOutputDir = "D:/project/demux_filtered";
    // Detect runs FIRST (call #1). total_count: 1 keeps the single-pool linear
    // path: detect -> ONE folded analyze (no separate run_combinatorial_demux).
    let phaseAtAnalyze: string | null | undefined = "unset";
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
      .mockImplementationOnce(async () => {
        // The slice sets analyzePhase='demux' before the folded analyze call;
        // the demux->analyze transition is driven later by progress.stage.
        phaseAtAnalyze = store.analyzePhase;
        return {
          verdicts: [],
          replicates: [],
          output_path: "D:/project/mame_result.xlsx",
          summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
          distribution_stats: distributionStats,
          reference_resolution: referenceResolution,
        };
      });

    await store.runAnalysis();

    expect(mockSendRequest).toHaveBeenCalledTimes(2);
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      1,
      "mame.detect_native_barcodes",
      expect.objectContaining({
        minknow_run_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      }),
    );
    // No mame.run_combinatorial_demux round-trip anymore.
    expect(mockSendRequest).not.toHaveBeenCalledWith(
      "mame.run_combinatorial_demux",
      expect.anything(),
      expect.anything(),
    );
    // Single folded analyze over the RAW run dir, carrying the demux knobs and
    // the 50-min raw-run timeout.
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      2,
      "analyze",
      expect.objectContaining({
        input_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
        reference: "D:/project/ref.fasta",
        ingest_mode: "barcode",
        custom_barcodes_xlsx: "D:/project/barcodes sequence.xlsx",
        native_barcodes: null,
        cds_start: 101,
        min_read_count: 47,
        wt_placement: "after_last_variant",
        coverage_fraction: 0.98,
        edit_dist_ratio: 0.25,
        chimera_split: true,
        demux_output_dir: demuxOutputDir,
        mapq_threshold: 25,
        trim_flank_bp: 30,
      }),
      3_000_000,
    );
    expect(phaseAtAnalyze).toBe("demux");
    expect(store.isAnalyzing).toBe(false);
    expect(store.analyzeMessage).toBe("Analysis complete");
    // Which reference the run actually read, routed from the response to the
    // store so the review screen can say the verdicts were scored against a
    // slice. This is the live path; the restore path is covered in
    // useAutosaveHydration.test.tsx. Carried through verbatim rather than
    // reshaped, so the notice and the sidecar cannot disagree about the span.
    expect(store.setReferenceResolution).toHaveBeenCalledWith(referenceResolution);
    const targetRound = useRoundStore.getState().rounds.find((round) => round.id === targetRoundId);
    expect(targetRound?.status).toBe("ngs_done");
    expect(targetRound?.genotype).toMatchObject({
      round_id: targetRoundId,
      verdict_xlsx: "D:/project/mame_result.xlsx",
      verdicts: [],
      replicates: [],
      evidence_signature: expect.stringMatching(/^fnv1a-[0-9a-f]{8}$/),
    });
  });

  it("forwards well_layout and selected_wells in the non-raw analyze path", async () => {
    // Regression: the consensus/sorted_barcode path used to omit per-well
    // scoping inputs, so every well was compared against the FULL expected
    // list and the plate plan rendered PASS wells as WRONG_AA.
    const wellLayout = { A01: "S65T", A02: "Y66H", H12: "WT" };
    const store = makeStore({
      inputDir: "D:/project/consensus",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "consensus",
      ingestMode: "barcode",
      selectedWells: ["A1", "B1"],
      wellLayout,
      cdsStart: 101,
      cdsEnd: 900,
      minFilteredDepth: 47,
      wtPlacement: "after_last_variant",
    });
    const targetRoundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });

    mockSendRequest.mockResolvedValueOnce({
      verdicts: [],
      replicates: [],
      output_path: "D:/project/mame_result.xlsx",
      summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
      distribution_stats: distributionStats,
    });

    await store.runAnalysis();

    expect(mockSendRequest).toHaveBeenCalledTimes(1);
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      1,
      "analyze",
      expect.objectContaining({
        input_dir: "D:/project/consensus",
        selected_wells: ["A1", "B1"],
        well_layout: wellLayout,
        cds_start: 101,
        min_read_count: 47,
        wt_placement: "after_last_variant",
      }),
      expect.anything(),
    );
    expect(store.isAnalyzing).toBe(false);
    expect(store.analyzeMessage).toBe("Analysis complete");
    const targetRound = useRoundStore.getState().rounds.find((round) => round.id === targetRoundId);
    expect(targetRound?.status).toBe("ngs_done");
    expect(targetRound?.genotype).toMatchObject({
      round_id: targetRoundId,
      verdict_xlsx: "D:/project/mame_result.xlsx",
      verdicts: [],
      replicates: [],
      completed_at: expect.any(String),
      evidence_signature: expect.stringMatching(/^fnv1a-[0-9a-f]{8}$/),
    });
  });

  it("forwards custom_barcodes_xlsx to validate_inputs so the raw-run guard sees it", async () => {
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
      cdsStart: 101,
      cdsEnd: 900,
      minFilteredDepth: 47,
      wtPlacement: "after_last_variant",
    });

    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    expect(mockSendRequest).toHaveBeenCalledWith(
      "validate_inputs",
      expect.objectContaining({
        input_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
        reference: "D:/project/ref.fasta",
        expected: "D:/project/KURO_expected.xlsx",
        custom_barcodes_xlsx: "D:/project/barcodes sequence.xlsx",
        cds_start: 101,
        min_read_count: 47,
        wt_placement: "after_last_variant",
      }),
    );
    expect(store.validationErrors).toEqual([]);
  });

  it("validates the same CDS, WT placement, and read-depth cutoff that analysis runs", async () => {
    const store = makeStore({
      inputDir: "D:/project/consensus",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "consensus",
      cdsStart: 101,
      cdsEnd: 900,
      minFilteredDepth: 47,
      wtPlacement: "after_last_variant",
    });
    mockSendRequest
      .mockResolvedValueOnce({ valid: true, errors: [] })
      .mockResolvedValueOnce({
        verdicts: [],
        replicates: [],
        output_path: "D:/project/mame_result.xlsx",
        summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
        distribution_stats: distributionStats,
      });

    await store.validateInputs();
    await store.runAnalysis();

    const validationPayload = mockSendRequest.mock.calls[0]?.[1] as Record<string, unknown>;
    const analyzePayload = mockSendRequest.mock.calls[1]?.[1] as Record<string, unknown>;
    for (const key of ["cds_start", "wt_placement", "min_read_count"] as const) {
      expect(validationPayload[key]).toBe(analyzePayload[key]);
    }
    expect(analyzePayload).toMatchObject({
      cds_start: 101,
      wt_placement: "after_last_variant",
      min_read_count: 47,
    });
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

    // Confirm with the user-selected native barcodes -> ONE folded analyze with
    // native_barcodes threaded (no separate run_combinatorial_demux round-trip).
    mockSendRequest.mockResolvedValueOnce({
      verdicts: [],
      replicates: [],
      output_path: "D:/project/mame_result.xlsx",
      summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
      distribution_stats: distributionStats,
    });

    await store.confirmNativeBarcodeSelection(["barcode06", "barcode20"]);

    expect(store.detectedNativeBarcodes).toBeNull();
    // Calls now: 1 detect (above) + 2 folded analyze.
    expect(mockSendRequest).toHaveBeenCalledTimes(2);
    expect(mockSendRequest).not.toHaveBeenCalledWith(
      "mame.run_combinatorial_demux",
      expect.anything(),
      expect.anything(),
    );
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      2,
      "analyze",
      expect.objectContaining({
        input_dir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
        ingest_mode: "barcode",
        native_barcodes: ["barcode06", "barcode20"],
        custom_barcodes_xlsx: "D:/project/barcodes sequence.xlsx",
        demux_output_dir: "D:/project/demux_filtered",
      }),
      3_000_000,
    );
    expect(store.isAnalyzing).toBe(false);
    expect(store.analyzeMessage).toBe("Analysis complete");
  });
  it("records the replicate axis in the namespace the records use", async () => {
    // The bug this pins: the dialog hands over MinKNOW directory names
    // (`barcode07`), which is what the demux needs to find
    // `fastq_pass/barcode07/`, while every record that comes back is stamped
    // with the demux OUTPUT directory (`sort_barcode07`). Storing the MinKNOW
    // form as the run's replicate axis makes every well look absent from every
    // plate. The two strings differ here on purpose.
    const store = makeStore({
      inputDir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "raw_run",
      rawRunParams: {
        ...makeStore().rawRunParams,
        customBarcodesPath: "D:/project/barcodes.xlsx",
      },
    });

    mockSendRequest.mockResolvedValueOnce({
      fastq_pass: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e/fastq_pass",
      min_share: 0.05,
      native_barcodes: [
        {
          name: "barcode07",
          sort_barcode_name: "sort_barcode07",
          fastq_bytes: 7_000_000,
          fastq_mb: 7.0,
          share: 0.5,
          is_used: true,
        },
        {
          name: "barcode08",
          sort_barcode_name: "sort_barcode08",
          fastq_bytes: 5_000_000,
          fastq_mb: 5.0,
          share: 0.35,
          is_used: true,
        },
        {
          name: "barcode09",
          sort_barcode_name: "sort_barcode09",
          fastq_bytes: 2_000_000,
          fastq_mb: 2.0,
          share: 0.15,
          is_used: false,
        },
      ],
      used_count: 2,
      total_count: 3,
    });

    await store.runAnalysis();
    expect(store.detectedBarcodeCount).toBe(3);

    mockSendRequest.mockResolvedValueOnce({
      verdicts: [],
      replicates: [],
      output_path: "D:/project/mame_result.xlsx",
      summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
      distribution_stats: distributionStats,
    });

    await store.confirmNativeBarcodeSelection(["barcode07", "barcode08"]);

    // The RPC keeps the MinKNOW names: that is where the FASTQ lives.
    expect(mockSendRequest).toHaveBeenNthCalledWith(
      2,
      "analyze",
      expect.objectContaining({ native_barcodes: ["barcode07", "barcode08"] }),
      3_000_000,
    );
    // The stored axis is the sort form, which is what verdict records carry.
    expect(store.selectedNativeBarcodes).toEqual([
      "sort_barcode07",
      "sort_barcode08",
    ]);
    expect(store.detectedBarcodeCount).toBe(3);
  });

  it("sends no native_barcodes at all when the operator pools the run", async () => {
    // Pooled is a stated answer, not a cancellation. The store keeps `[]`
    // (one plate), while the RPC gets null: the Pydantic validator on
    // `native_barcodes` rejects an empty list.
    const store = makeStore({
      inputDir: "D:/runs/20260212_2227_X4_FBF10847_e7145f8e",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "raw_run",
      rawRunParams: {
        ...makeStore().rawRunParams,
        customBarcodesPath: "D:/project/barcodes.xlsx",
      },
      detectedNativeBarcodes: [
        {
          name: "barcode07",
          sort_barcode_name: "sort_barcode07",
          fastq_bytes: 7_000_000,
          fastq_mb: 7.0,
          share: 0.6,
          is_used: true,
        },
      ],
      detectedBarcodeCount: 3,
    });

    mockSendRequest.mockResolvedValueOnce({
      verdicts: [],
      replicates: [],
      output_path: "D:/project/mame_result.xlsx",
      summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
      distribution_stats: distributionStats,
    });

    await store.confirmNativeBarcodeSelection([]);

    expect(mockSendRequest).toHaveBeenNthCalledWith(
      1,
      "analyze",
      expect.objectContaining({ native_barcodes: null }),
      3_000_000,
    );
    expect(store.selectedNativeBarcodes).toEqual([]);
    expect(store.detectedBarcodeCount).toBe(3);
  });

  it("keeps an in-flight ordinary analysis bound to its originating round", async () => {
    const store = makeStore({
      inputDir: "D:/project/consensus",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "consensus",
    });
    const firstRoundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });
    const result = {
      verdicts: [],
      replicates: [],
      output_path: "D:/project/mame_result.xlsx",
      summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
      distribution_stats: distributionStats,
    };
    let resolveAnalyze = (_result: typeof result) => {};
    mockSendRequest.mockImplementationOnce(
      () =>
        new Promise<typeof result>((resolve) => {
          resolveAnalyze = resolve;
        }),
    );

    const pending = store.runAnalysis();
    await Promise.resolve();
    const secondRoundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });
    resolveAnalyze(result);
    await pending;

    const rounds = useRoundStore.getState().rounds;
    expect(rounds.find((round) => round.id === firstRoundId)).toMatchObject({
      status: "ngs_done",
      genotype: expect.objectContaining({
        round_id: firstRoundId,
        verdict_xlsx: "D:/project/mame_result.xlsx",
      }),
    });
    expect(rounds.find((round) => round.id === secondRoundId)).toMatchObject({
      status: "design",
      genotype: {},
    });
  });

  it("does not overwrite existing round evidence when analysis fails", async () => {
    const store = makeStore({
      inputDir: "D:/project/consensus",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "consensus",
    });
    const targetRoundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });
    const existingEvidence = { verdict_xlsx: "D:/project/previous.xlsx", run_id: "previous" };
    useRoundStore.getState().updateRoundField(targetRoundId, "genotype", existingEvidence);
    mockSendRequest.mockRejectedValueOnce(new Error("sidecar failed"));

    await store.runAnalysis();

    expect(useRoundStore.getState().rounds.find((round) => round.id === targetRoundId)).toMatchObject({
      status: "design",
      genotype: existingEvidence,
    });
  });

  it("completes without writing round evidence when no round is active", async () => {
    const store = makeStore({
      inputDir: "D:/project/consensus",
      expectedPath: "D:/project/KURO_expected.xlsx",
      referencePath: "D:/project/ref.fasta",
      outputPath: "D:/project",
      inputMode: "consensus",
    });
    mockSendRequest.mockResolvedValueOnce({
      verdicts: [],
      replicates: [],
      output_path: "D:/project/mame_result.xlsx",
      summary: { total: 0, pass_count: 0, ambiguous_count: 0, fail_count: 0 },
      distribution_stats: distributionStats,
    });

    await store.runAnalysis();

    expect(useRoundStore.getState().rounds).toEqual([]);
    expect(store.analyzeMessage).toBe("Analysis complete");
  });
});
