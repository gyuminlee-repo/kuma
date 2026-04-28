import type { StateCreator } from "zustand";
import { cancelAndRespawn, sendRequest } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import { loadWorkspaceFromFile, saveWorkspaceToFile } from "@/lib/mame/workspace";
import type { AnalyzeResult, ValidationResult } from "@/types/mame/models";
import type { KumaProject } from "@/state/projectContext";
import type { InputSlice } from "../slice-interfaces";
import type { AppState } from "../types";

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => ({
  inputDir: "",
  expectedPath: "",
  referencePath: "",
  outputPath: "",
  mode: "amplicon",
  ingestMode: "barcode",
  cdsStart: 0,
  cdsEnd: 0,
  minFileSizeKb: 50,
  manyCutoff: 5,
  validationErrors: [],
  isValidating: false,
  isAnalyzing: false,
  analyzeProgress: 0,
  analyzeMessage: "Waiting for sidecar connection",
  setInputDir: (inputDir) => set({ inputDir }),
  setExpectedPath: (expectedPath) => set({ expectedPath }),
  setReferencePath: (referencePath) => set({ referencePath }),
  setOutputPath: (outputPath) => set({ outputPath }),
  setParams: (params) =>
    set((state) => ({
      mode: params.mode ?? state.mode,
      ingestMode: params.ingestMode ?? state.ingestMode,
      cdsStart: params.cdsStart ?? state.cdsStart,
      cdsEnd: params.cdsEnd ?? state.cdsEnd,
      minFileSizeKb: params.minFileSizeKb ?? state.minFileSizeKb,
      manyCutoff: params.manyCutoff ?? state.manyCutoff,
    })),
  setValidationErrors: (validationErrors) => set({ validationErrors }),
  setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
  setAnalyzeProgress: (analyzeProgress) => set({ analyzeProgress }),
  setAnalyzeMessage: (analyzeMessage) => set({ analyzeMessage }),
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
      await get().loadPlateData();
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
