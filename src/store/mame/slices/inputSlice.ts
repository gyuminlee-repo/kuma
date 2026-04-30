import type { StateCreator } from "zustand";
import { cancelAndRespawn, sendRequest } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import { loadWorkspaceFromFile, saveWorkspaceToFile } from "@/lib/mame/workspace";
import type {
  AnalyzeResult,
  DemuxAndFilterResult,
  DistributionStats,
  ValidationResult,
} from "@/types/mame/models";
import type { KumaProject } from "@/state/projectContext";
import type { InputSlice, InputMode, RawRunParams } from "../slice-interfaces";
import type { AppState } from "../types";

const DEFAULT_RAW_RUN_PARAMS: RawRunParams = {
  customBarcodesPath: "",
  sequencingSummaryPath: "",
  minQscore: 8.0,
  lengthMin: 800,
  lengthMax: 3000,
  minBarcodeScore: 60.0,
};

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => ({
  inputDir: "",
  expectedPath: "",
  referencePath: "",
  outputPath: "",
  mode: "amplicon",
  ingestMode: "barcode",
  inputMode: "sorted_barcode",
  rawRunParams: { ...DEFAULT_RAW_RUN_PARAMS },
  cdsStart: 0,
  cdsEnd: 0,
  minFileSizeKb: 50,
  manyCutoff: 5,
  validationErrors: [],
  isValidating: false,
  isAnalyzing: false,
  isDemuxing: false,
  analyzeProgress: 0,
  analyzeMessage: "Waiting for sidecar connection",
  demuxProgress: 0,
  demuxMessage: "",
  demuxResult: null,
  distributionStats: null,
  setInputDir: (inputDir) => set({ inputDir }),
  setExpectedPath: (expectedPath) => set({ expectedPath }),
  setReferencePath: (referencePath) => set({ referencePath }),
  setOutputPath: (outputPath) => set({ outputPath }),
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
      manyCutoff: params.manyCutoff ?? state.manyCutoff,
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
  runDemuxAndFilter: async () => {
    const s = get();
    const { rawRunParams } = s;
    if (!rawRunParams.customBarcodesPath) {
      set({ validationErrors: ["Custom barcodes file path is required for raw run mode"] });
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
          output_dir: s.outputPath ? `${s.outputPath}_demux` : "",
          sequencing_summary: rawRunParams.sequencingSummaryPath || undefined,
          min_qscore: rawRunParams.minQscore,
          length_min: rawRunParams.lengthMin,
          length_max: rawRunParams.lengthMax,
          min_barcode_score: rawRunParams.minBarcodeScore,
        },
        600_000,
      );
      set({
        isDemuxing: false,
        demuxProgress: 100,
        demuxMessage: `Demux complete: ${result.n_assigned} reads assigned`,
        demuxResult: result,
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
      const result = await sendRequest<AnalyzeResult>(
        "analyze",
        {
          input_dir: get().inputDir,
          reference: get().referencePath,
          expected: get().expectedPath,
          output: get().outputPath,
          mode: get().mode,
          ingest_mode: get().ingestMode,
          cds_start: get().cdsStart,
          cds_end: get().cdsEnd,
          min_file_size_kb: get().minFileSizeKb,
          many_cutoff: get().manyCutoff,
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
  saveWorkspace: async (project: KumaProject) => {
    const s = get();
    try {
      const savedTo = await saveWorkspaceToFile(
        {
          version: 1,
          inputDir: s.inputDir,
          expectedPath: s.expectedPath,
          referencePath: s.referencePath,
          outputPath: s.outputPath,
          mode: s.mode,
          ingestMode: s.ingestMode,
          inputMode: s.inputMode,
          rawRunParams: s.rawRunParams,
          cdsStart: s.cdsStart,
          cdsEnd: s.cdsEnd,
          minFileSizeKb: s.minFileSizeKb,
          manyCutoff: s.manyCutoff,
        },
        project,
      );
      if (savedTo) set({ analyzeMessage: `Workspace saved: ${savedTo}` });
    } catch (error) {
      set({ analyzeMessage: `Workspace save failed: ${formatError(error)}` });
    }
  },
  loadWorkspace: async (project: KumaProject) => {
    try {
      const snap = await loadWorkspaceFromFile(project);
      if (!snap) return;
      set({
        inputDir: snap.inputDir,
        expectedPath: snap.expectedPath,
        referencePath: snap.referencePath,
        outputPath: snap.outputPath,
        mode: snap.mode,
        ingestMode: snap.ingestMode,
        inputMode: (snap.inputMode as InputMode | undefined) ?? "sorted_barcode",
        rawRunParams: snap.rawRunParams ?? { ...DEFAULT_RAW_RUN_PARAMS },
        cdsStart: snap.cdsStart,
        cdsEnd: snap.cdsEnd,
        minFileSizeKb: snap.minFileSizeKb,
        manyCutoff: snap.manyCutoff,
        validationErrors: [],
        analyzeMessage: "Workspace loaded",
      });
    } catch (error) {
      set({ analyzeMessage: `Workspace load failed: ${formatError(error)}` });
    }
  },
});
