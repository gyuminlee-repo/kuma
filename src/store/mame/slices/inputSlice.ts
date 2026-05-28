import type { StateCreator } from "zustand";
import { cancelAndRespawn, sendRequest } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import type {
  AmpliconLengthEstimate,
  AnalyzeResult,
  DemuxAndFilterResult,
  DistributionStats,
  ValidationResult,
} from "@/types/mame/models";
import type { CdsCandidate } from "@/lib/sequence/autoDetectCds";
import type { CombinatorialDemuxResult } from "@/types/mame/combinatorial_demux";
import type { InputSlice, RawRunParams } from "../slice-interfaces";
import type { AppState } from "../types";

interface ParseReferenceResult {
  cds_candidates: CdsCandidate[];
  sequence_length: number;
  format: "fasta" | "genbank" | "snapgene";
}

const DEFAULT_RAW_RUN_PARAMS: RawRunParams = {
  customBarcodesPath: "",
  sequencingSummaryPath: "",
  minQscore: 8.0,
  lengthMin: 800,
  lengthMax: 3000,
  minBarcodeScore: 60.0,
  // R6.5 defaults
  targetLength: null,
  lengthToleranceBp: 30,
  linkedTrim: false,
  revPrimerUniversal: "",
  normalizeHeaders: true,
  // PR-A: combinatorial demux advanced defaults
  coverageFraction: 0.98,
  editDistRatio: 0.25,
  chimeraSplit: true,
};

function pickLongestIndex(candidates: CdsCandidate[]): number | null {
  if (candidates.length === 0) return null;
  let best = 0;
  let bestLen = candidates[0].end - candidates[0].start;
  for (let i = 1; i < candidates.length; i++) {
    const len = candidates[i].end - candidates[i].start;
    if (len > bestLen) {
      best = i;
      bestLen = len;
    }
  }
  return best;
}

function deriveDemuxOutputDir(outputPath: string): string {
  const normalized = outputPath.replace(/\\/g, "/");
  const slashIdx = normalized.lastIndexOf("/");
  const dir = slashIdx >= 0 ? outputPath.slice(0, slashIdx) : "";
  return dir ? `${dir}/demux_filtered` : "demux_filtered";
}

function getDemuxInputErrors(state: AppState): string[] {
  const errors: string[] = [];
  if (!state.inputDir) errors.push("MinKNOW run folder is required.");
  if (!state.rawRunParams.customBarcodesPath) {
    errors.push("Custom Barcodes (.xlsx or .csv) file is required.");
  }
  if (!state.outputPath) errors.push("Export destination folder is required.");
  if (state.rawRunParams.linkedTrim && !state.rawRunParams.revPrimerUniversal) {
    errors.push("Universal Rev Primer is required when Trim Adapters is enabled.");
  }
  return errors;
}

const mameInputInitialState = {
  inputDir: "",
  expectedPath: "",
  referencePath: "",
  outputPath: "",
  sampleMapPath: "",
  mode: "amplicon" as const,
  ingestMode: "barcode" as const,
  inputMode: "raw_run" as const,
  rawRunParams: { ...DEFAULT_RAW_RUN_PARAMS },
  cdsStart: 0,
  cdsEnd: 0,
  minFileSizeKb: 50,
  minFilteredDepth: 15,
  manyCutoff: 5,
  validationErrors: [] as string[],
  isValidating: false,
  isAnalyzing: false,
  isDemuxing: false,
  analyzeProgress: 0,
  analyzeMessage: "Waiting for sidecar connection",
  demuxProgress: 0,
  demuxMessage: "",
  demuxResult: null,
  distributionStats: null,
  ampliconLengthEstimate: null,
  cdsCandidates: [],
  selectedCdsIndex: 0,
  analyzeCdsCandidates: [] as CdsCandidate[],
  selectedAnalyzeCdsIndex: null as number | null,
  sharedFastaPath: null as string | null,
  sharedEvolveproCsvPath: null as string | null,
  resetEpoch: 0,
};

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => ({
  ...mameInputInitialState,
  setCdsCandidates: (cdsCandidates) => set({ cdsCandidates, selectedCdsIndex: 0 }),
  setSelectedCdsIndex: (selectedCdsIndex) => set({ selectedCdsIndex }),
  setAnalyzeCdsCandidates: (analyzeCdsCandidates) => {
    const idx = pickLongestIndex(analyzeCdsCandidates);
    set({
      analyzeCdsCandidates,
      selectedAnalyzeCdsIndex: idx,
      ...(idx !== null
        ? { cdsStart: analyzeCdsCandidates[idx].start, cdsEnd: analyzeCdsCandidates[idx].end }
        : {}),
    });
  },
  setSelectedAnalyzeCdsIndex: (selectedAnalyzeCdsIndex) =>
    set({ selectedAnalyzeCdsIndex }),
  refreshAnalyzeCdsCandidates: async (referencePath: string) => {
    if (!referencePath) {
      set({ analyzeCdsCandidates: [], selectedAnalyzeCdsIndex: null });
      return;
    }
    try {
      const result = await sendRequest<ParseReferenceResult>(
        "mame.ingest.parse_reference",
        { path: referencePath },
        15_000,
      );
      // Race guard: only commit if the referencePath has not changed since the
      // call was issued (user may have picked another file mid-flight).
      if (get().referencePath !== referencePath) return;
      const candidates = result.cds_candidates ?? [];
      const idx = pickLongestIndex(candidates);
      set({
        analyzeCdsCandidates: candidates,
        selectedAnalyzeCdsIndex: idx,
        ...(idx !== null
          ? { cdsStart: candidates[idx].start, cdsEnd: candidates[idx].end }
          : {}),
      });
    } catch (error) {
      // Silent fallback to manual entry; surface as console warn only.
      console.warn("[inputSlice] parse_reference failed:", error);
      if (get().referencePath !== referencePath) return;
      set({ analyzeCdsCandidates: [], selectedAnalyzeCdsIndex: null });
    }
  },
  setSharedFastaPath: (sharedFastaPath) => set({ sharedFastaPath }),
  setSharedEvolveproCsvPath: (sharedEvolveproCsvPath) => set({ sharedEvolveproCsvPath }),
  bumpResetEpoch: () => set((s) => ({ resetEpoch: s.resetEpoch + 1 })),
  setInputDir: (inputDir) => set({ inputDir, validationErrors: [] }),
  setExpectedPath: (expectedPath) => set({ expectedPath, validationErrors: [] }),
  setReferencePath: (referencePath) => {
    set({ referencePath, validationErrors: [] });
    void get().refreshAnalyzeCdsCandidates(referencePath);
  },
  setOutputPath: (outputPath) => set({ outputPath, validationErrors: [] }),
  setSampleMapPath: (sampleMapPath) => set({ sampleMapPath }),
  setParams: (params) =>
    set((state) => ({
      mode: params.mode ?? state.mode,
      ingestMode: params.ingestMode ?? state.ingestMode,
      inputMode: params.inputMode ?? state.inputMode,
      rawRunParams:
        params.rawRunParams != null
          ? { ...state.rawRunParams, ...params.rawRunParams }
          : state.rawRunParams,
      cdsStart: params.cdsStart ?? state.cdsStart,
      cdsEnd: params.cdsEnd ?? state.cdsEnd,
      minFileSizeKb: params.minFileSizeKb ?? state.minFileSizeKb,
      minFilteredDepth: params.minFilteredDepth ?? state.minFilteredDepth,
      manyCutoff: params.manyCutoff ?? state.manyCutoff,
      validationErrors: [],
    })),
  setValidationErrors: (validationErrors) => set({ validationErrors }),
  setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
  setIsDemuxing: (isDemuxing) => set({ isDemuxing }),
  setAnalyzeProgress: (analyzeProgress) => set({ analyzeProgress }),
  setAnalyzeMessage: (analyzeMessage) => set({ analyzeMessage }),
  setDemuxProgress: (demuxProgress) => set({ demuxProgress }),
  setDemuxMessage: (demuxMessage) => set({ demuxMessage }),
  setDemuxResult: (demuxResult: DemuxAndFilterResult | null) => set({ demuxResult }),
  setDistributionStats: (distributionStats: DistributionStats | null) =>
    set({ distributionStats }),
  setAmpliconLengthEstimate: (ampliconLengthEstimate: AmpliconLengthEstimate | null) =>
    set({ ampliconLengthEstimate }),
  runDemuxAndFilter: async () => {
    const s = get();
    const { rawRunParams } = s;
    const inputErrors = getDemuxInputErrors(s);
    if (inputErrors.length > 0) {
      set({ validationErrors: inputErrors, demuxMessage: "Demux setup incomplete" });
      return;
    }
    set({
      isDemuxing: true,
      demuxProgress: 0,
      demuxMessage: "Starting demux...",
      validationErrors: [],
      demuxResult: null,
    });
    try {
      const result = await sendRequest<DemuxAndFilterResult>(
        "demux_and_filter",
        {
          fastq_dir: s.inputDir,
          custom_barcodes_path: rawRunParams.customBarcodesPath,
          output_dir: deriveDemuxOutputDir(s.outputPath),
          sequencing_summary: rawRunParams.sequencingSummaryPath || undefined,
          min_qscore: rawRunParams.minQscore,
          length_min: rawRunParams.lengthMin,
          length_max: rawRunParams.lengthMax,
          min_barcode_score: rawRunParams.minBarcodeScore,
          target_length: rawRunParams.targetLength ?? undefined,
          length_tolerance_bp: rawRunParams.lengthToleranceBp,
          auto_detect_length: rawRunParams.targetLength === null,
          linked_trim: rawRunParams.linkedTrim,
          rev_primer_universal: rawRunParams.revPrimerUniversal || undefined,
          normalize_headers: rawRunParams.normalizeHeaders,
        },
        600_000,
      );
      set({
        isDemuxing: false,
        demuxProgress: 100,
        demuxMessage: `Demux complete: ${result.n_assigned.toLocaleString()} reads assigned`,
        demuxResult: result,
        ampliconLengthEstimate: result.amplicon_length_estimate,
        // Auto-set inputDir to demux output for downstream analyze call.
        inputDir: result.output_dir,
        ingestMode: "barcode",
      });
    } catch (error) {
      set({
        isDemuxing: false,
        demuxProgress: 0,
        demuxMessage: "Demux failed",
        validationErrors: [formatError(error)],
      });
    }
  },
  validateInputs: async () => {
    set({ isValidating: true, validationErrors: [] });
    try {
      const result = await sendRequest<ValidationResult>("validate_inputs", {
        input_dir: get().inputDir,
        reference: get().referencePath,
        expected: get().expectedPath,
        cds_end: get().cdsEnd,
      });
      set({
        validationErrors: result.errors,
        isValidating: false,
        analyzeMessage: result.valid ? "Validation complete" : "Validation errors found",
      });
    } catch (error) {
      set({
        validationErrors: [formatError(error)],
        isValidating: false,
        analyzeMessage: "Validation failed",
      });
    }
  },
  runAnalysis: async () => {
    set({
      isAnalyzing: true,
      analyzeProgress: 0,
      analyzeMessage: "Starting analysis",
      validationErrors: [],
    });
    try {
      const state = get();
      let analysisInputDir = state.inputDir;
      let analysisIngestMode = state.ingestMode;

      if (state.inputMode === "raw_run") {
        const { rawRunParams } = state;
        const inputErrors = getDemuxInputErrors(state);
        if (inputErrors.length > 0) {
          throw new Error(inputErrors.join("\n"));
        }

        const combinatorialOutputDir = deriveDemuxOutputDir(state.outputPath);
        set({
          analyzeProgress: 3,
          analyzeMessage: "Running combinatorial demux from raw MinKNOW run",
        });
        const demuxResult = await sendRequest<CombinatorialDemuxResult>(
          "mame.run_combinatorial_demux",
          {
            minknow_run_dir: state.inputDir,
            custom_barcodes_xlsx: rawRunParams.customBarcodesPath,
            reference_fasta: state.referencePath,
            output_dir: combinatorialOutputDir,
            sample_map_xlsx: state.sampleMapPath || null,
            kuro_xlsx: null,
            mapq_threshold: 25,
            coverage_fraction: rawRunParams.coverageFraction,
            edit_dist_ratio: rawRunParams.editDistRatio,
            chimera_split: rawRunParams.chimeraSplit,
            trim_flank_bp: 30,
          },
          600_000,
        );
        analysisInputDir = demuxResult.output_dir;
        analysisIngestMode = "barcode";
        set({
          analyzeProgress: 15,
          analyzeMessage: `Combinatorial demux complete: ${demuxResult.assigned_reads.toLocaleString()} reads assigned`,
        });
      }

      const result = await sendRequest<AnalyzeResult>(
        "analyze",
        {
          input_dir: analysisInputDir,
          reference: state.referencePath,
          expected: state.expectedPath,
          output: state.outputPath,
          mode: state.mode,
          ingest_mode: analysisIngestMode,
          cds_start: state.cdsStart,
          cds_end: state.cdsEnd,
          min_file_size_kb: state.minFileSizeKb,
          many_cutoff: state.manyCutoff,
        },
        300_000,
      );

      get().setVerdicts(result.verdicts);
      get().setReplicates(result.replicates);
      get().setSummary(result.summary);
      get().setOutputPath(result.output_path);
      get().setDistributionStats(result.distribution_stats ?? null);
      await get().loadPlateData();
      // A8: auto-load run health after analysis completes (non-blocking on failure)
      void get().loadRunHealth();
      set({
        isAnalyzing: false,
        analyzeProgress: 100,
        analyzeMessage: "Analysis complete",
      });
    } catch (error) {
      set({
        isAnalyzing: false,
        analyzeMessage: "Analysis failed",
        validationErrors: [formatError(error)],
      });
    }
  },
  cancelAnalysis: async () => {
    if (!get().isAnalyzing) return;
    set({ analyzeMessage: "Cancelling…" });
    try {
      await cancelAndRespawn();
    } catch (error) {
      console.warn("[inputSlice] cancel failed:", error);
    }
    set({
      isAnalyzing: false,
      analyzeProgress: 0,
      analyzeMessage: "Analysis cancelled",
    });
  },
  resetInput: () => set({ ...mameInputInitialState }),
});
