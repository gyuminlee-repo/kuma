import type { StateCreator } from "zustand";
import { cancelAndRespawn, sendRequest } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import { defaultMameExportFilename } from "@/lib/mameFilename";
import { writeMameResultSnapshot } from "@/lib/mame/resultSnapshot";
import { pickAnalyzeYield } from "@/lib/mame/analyzeYield";
import { isPlateOrderReportable } from "@/lib/mame/plateOrderMessage";
// Store-free module on purpose: `janus.ts` imports this store, so importing
// it here would close a module-eval cycle.
import {
  loadJanusSettings,
  saveJanusSettings,
  toRpcParams,
} from "@/lib/mame/janusSettings";
import type {
  AmpliconLengthEstimate,
  AnalyzeResult,
  DemuxAndFilterResult,
  DistributionStats,
  JanusAutosaveResult,
  JanusExportSettings,
  BarcodeAxisCounts,
  LegacySampleMapFinding,
  PlateOrderFinding,
  PlateOrderReport,
  ValidationResult,
} from "@/types/mame/models";
import type { CdsCandidate } from "@/lib/sequence/autoDetectCds";
import type { VariantSourceInfo } from "@/types/mame/barcode_package";

import type { WellLayout, WtPlacement } from "@/types/mame/well_layout";
import type { DetectNativeBarcodesResult } from "@/types/mame/detect_native_barcodes";
import type { InputSlice, RawRunParams } from "../slice-interfaces";
import type { AppState } from "../types";
import { useRoundStore } from "@/store/round/roundSlice";
const MAME_DEMUX_RPC_TIMEOUT_MS = 1_800_000; // 30 min — demux of large runs (78 FASTQ incident)
const MAME_ANALYZE_RPC_TIMEOUT_MS = 1_200_000; // 20 min — full analysis pipeline
const MAME_RAWRUN_RPC_TIMEOUT_MS = 3_000_000; // 50 min >= demux(30m)+analyze(20m) for folded raw-run analyze


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
  // R6.5 defaults
  targetLength: null,
  lengthToleranceBp: 30,
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

/**
 * Wall-clock milliseconds since `startedAt`, or null when the run carried no
 * start stamp. Reads the same `analyzeStartedAt` clock the in-run ETA uses, so
 * the reported duration and the ETA cannot disagree about when a run began.
 */
function elapsedSince(startedAt: number | null): number | null {
  if (startedAt === null) return null;
  const elapsed = Date.now() - startedAt;
  return elapsed >= 0 ? elapsed : null;
}
function jsonEvidenceSnapshot(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value) ?? "null") as unknown;
}

function stableEvidenceSignature(value: unknown): string {
  const text = JSON.stringify(value) ?? "null";
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `fnv1a-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function createAnalyzeRunId(): string {
  return `analyze-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function persistRoundAnalyzeEvidence(
  targetRoundId: string | null,
  runId: string,
  result: AnalyzeResult,
): void {
  if (targetRoundId === null) return;

  const completedAt = new Date().toISOString();
  const evidence = {
    run_id: runId,
    round_id: targetRoundId,
    verdict_xlsx: result.output_path,
    verdicts: jsonEvidenceSnapshot(result.verdicts),
    replicates: jsonEvidenceSnapshot(result.replicates),
    completed_at: completedAt,
  };

  const roundStore = useRoundStore.getState();
  roundStore.updateRoundField(targetRoundId, "genotype", {
    ...evidence,
    evidence_signature: stableEvidenceSignature(evidence),
  });
  roundStore.transitionStatus(targetRoundId, "ngs_done");
}

/** Join cross-platform path segments. */
function joinPathSlice(dir: string, filename: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return `${dir.replace(/[\/]+$/, "")}${sep}${filename}`;
}

/** outputPath is now a folder; append /demux_filtered directly. */
function deriveDemuxOutputDir(outputFolder: string): string {
  const trimmed = outputFolder.replace(/[\/]+$/, "");
  if (!trimmed) return "demux_filtered";
  const sep = trimmed.includes("\\") ? "\\" : "/";
  return `${trimmed}${sep}demux_filtered`;
}

function getDemuxInputErrors(state: AppState): string[] {
  const errors: string[] = [];
  if (!state.inputDir) errors.push("MinKNOW run folder is required.");
  if (!state.rawRunParams.customBarcodesPath) {
    errors.push("Custom Barcodes (.xlsx or .csv) file is required.");
  }
  if (!state.outputPath) errors.push("Export destination folder is required.");
  return errors;
}

const mameInputInitialState = {
  inputDir: "",
  expectedPath: "",
  referencePath: "",
  outputPath: "",
  selectedWells: null as string[] | null,
  wellSelectionOccupants: null as number | null,
  wtPlacement: "last_well" as WtPlacement,
  wtWell: null as string | null,
  legacySampleMapPath: null as string | null,
  projectPath: null as string | null,
  mode: "amplicon" as const,
  ingestMode: "barcode" as const,
  inputMode: "raw_run" as const,
  rawRunParams: { ...DEFAULT_RAW_RUN_PARAMS },
  cdsStart: 0,
  cdsEnd: 0,
  minFileSizeKb: 50,
  // The sidecar's fallback is 30. Keep the form at that value too: this is
  // the primary verdict cutoff, so displaying 15 while applying 30 would make
  // an untouched project silently report a different analysis.
  minFilteredDepth: 30,
  manyCutoff: 5,
  maxConsensusNFraction: 0.0,
  validationErrors: [] as string[],
  isValidating: false,
  isAnalyzing: false,
  isDemuxing: false,
  analyzeProgress: 0,
  analyzeMessage: "Waiting for sidecar connection",
  analyzeCurrent: null as number | null,
  analyzeTotal: null as number | null,
  analyzeStage: null as string | null,
  analyzeStartedAt: null as number | null,
  analyzeDurationMs: null as number | null,
  analyzePhase: null as "demux" | "analyze" | null,
  demuxProgress: 0,
  demuxMessage: "",
  demuxResult: null,
  distributionStats: null,
  ampliconLengthEstimate: null,
  detectedNativeBarcodes: null as DetectNativeBarcodesResult["native_barcodes"] | null,
  isDetectingBarcodes: false,
  selectedNativeBarcodes: null as string[] | null,
  detectedBarcodeCount: null as number | null,
  cdsCandidates: [],
  selectedCdsIndex: 0,
  analyzeCdsCandidates: [] as CdsCandidate[],
  selectedAnalyzeCdsIndex: null as number | null,
  sharedFastaPath: null as string | null,
  sharedEvolveproCsvPath: null as string | null,
  resetEpoch: 0,
  wellLayout: null as WellLayout | null,
  plateOrderFinding: null as PlateOrderFinding | null,
  legacySampleMapFinding: null as LegacySampleMapFinding | null,
  barcodeAxisCounts: null as BarcodeAxisCounts | null,
  variantSourceInfo: null as VariantSourceInfo | null,
  variantSheet: null as string | null,
  variantColumn: null as string | null,
  variantSelectionExplicit: false,
  janusSettings: loadJanusSettings(),
  janusAutosave: null as JanusAutosaveResult | null,
  janusMappingAutosave: null as JanusAutosaveResult | null,
};

/**
 * The variant-list reading choice, in RPC form.
 *
 * One helper for every call that reads the expected list (validate_inputs and
 * both analyze paths): sending different values from different calls would have
 * the validation and the run look at different rows of the same file. Omitted
 * entirely while nothing is chosen, which is the pre-v0.15.6 behaviour.
 */
function variantSourceParams(state: AppState): Record<string, string> {
  return {
    ...(state.variantSheet ? { variant_sheet: state.variantSheet } : {}),
    ...(state.variantColumn ? { variant_column: state.variantColumn } : {}),
  };
}

/**
 * Inputs that define the analysis must be identical for validation and both
 * analyze paths. In particular, `validate_inputs` skips CDS bounds checks
 * without `cds_start`, while `wt_placement` changes the plate-capacity
 * findings; separate literals had allowed both checks to describe another run.
 */
function analyzeInputParams(state: AppState) {
  return {
    input_dir: state.inputDir,
    reference: state.referencePath,
    expected: state.expectedPath,
    cds_start: state.cdsStart,
    cds_end: state.cdsEnd,
    min_file_size_kb: state.minFileSizeKb,
    min_read_count: state.minFilteredDepth,
    many_cutoff: state.manyCutoff,
    max_consensus_n_fraction: state.maxConsensusNFraction,
    well_layout: state.wellLayout ?? null,
    selected_wells: state.selectedWells,
    wt_placement: state.wtPlacement,
    legacy_sample_map_xlsx: state.legacySampleMapPath,
    ...variantSourceParams(state),
  };
}

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
  // A completed run's outputs (verdicts, wells, the Janus autosave banners,
  // ...) describe the PREVIOUS inputDir. Re-picking the same folder changes
  // nothing about what those outputs mean, so only an actual change clears
  // them; picking the same value twice (e.g. re-confirming via the same
  // dialog) must not wipe a result the operator has not touched yet.
  setInputDir: (inputDir) => {
    const changed = get().inputDir !== inputDir;
    set({ inputDir, validationErrors: [] });
    if (changed) get().clearResults();
  },
  // A finding describes one workbook, and a mapping names columns of one file.
  // Pointing at another file makes both statements about a file nobody is
  // running: the sheet and column chosen for the previous one would silently
  // name rows in this one. The panel re-checks and re-inspects the new file
  // right after (see `checkExpectedPlateOrder`, `inspectVariantSource`).
  //
  // The expected-mutations workbook also names what a completed run's
  // verdicts were graded against, so swapping it invalidates that run's
  // outputs the same way a swapped inputDir does (see `setInputDir` above).
  //
  // It also decides who is on the plate, which is why the well selection goes
  // with it. The assignment rule is "occupant i takes the i-th selected well",
  // so a selection made for one variant list places a DIFFERENT list when the
  // file changes: the wells look deliberate and every one of them holds
  // something else. Dropping it back to null re-seats the new list on the
  // leading wells, which is the only placement the new file states.
  setExpectedPath: (expectedPath) => {
    const changed = get().expectedPath !== expectedPath;
    set({
      expectedPath,
      validationErrors: [],
      plateOrderFinding: null,
      variantSourceInfo: null,
      variantSheet: null,
      variantColumn: null,
      variantSelectionExplicit: false,
      selectedWells: null,
      wellSelectionOccupants: null,
      wtWell: null,
    });
    if (changed) get().clearResults();
  },
  /**
   * Ask what the picked variant list offers, and preselect what the backend
   * would read on its own.
   *
   * Preselecting the auto-detected column (rather than leaving the picker
   * empty) means the displayed mapping is the mapping that runs. A KURO export
   * needs no mapping at all, so the panel hides itself off `is_kuro_export`.
   * A sidecar too old for this method leaves `variantSourceInfo` null, which is
   * the pre-v0.15.6 behaviour: KURO exports only, no picker.
   */
  inspectVariantSource: async (path: string) => {
    if (!path) {
      set({
        variantSourceInfo: null,
        variantSheet: null,
        variantColumn: null,
        variantSelectionExplicit: false,
      });
      return;
    }
    try {
      const info = await sendRequest<VariantSourceInfo>(
        "inspect_variant_source",
        { path },
        30_000,
      );
      if (get().expectedPath !== path) return;
      set({
        variantSourceInfo: info,
        // Sheet stays unset for a KURO export: the backend already knows which
        // sheet it reads, and naming it here would only be a second way to say
        // the same thing.
        variantSheet: info.is_kuro_export ? null : (info.sheets[0] ?? null),
        variantColumn: info.is_kuro_export ? null : info.suggested_column,
        variantSelectionExplicit: false,
      });
    } catch {
      if (get().expectedPath !== path) return;
      set({ variantSourceInfo: null });
    }
  },
  // The sheet and column decide WHICH ROWS are read, so they define a
  // different campaign just as much as the workbook path does. The well
  // selection must be re-declared for that campaign; it narrows the fixed
  // draft layout and never re-seats occupants. Routed through
  // `setSelectedWells` so its own change invalidates results once.
  setVariantSheet: (variantSheet) => {
    const state = get();
    if (state.variantSheet === variantSheet) return;
    const selectionWasEmpty = state.selectedWells === null;
    set({
      variantSheet,
      // The headers differ per sheet, so the column chosen for the old one
      // cannot be carried over.
      variantColumn: null,
      variantSelectionExplicit: true,
      validationErrors: [],
      wellSelectionOccupants: null,
    });
    get().setSelectedWells(null);
    // The sheet itself changes the expected rows even with no declared wells,
    // when `setSelectedWells(null)` is intentionally a no-op.
    if (selectionWasEmpty) get().clearResults();
  },
  setVariantColumn: (variantColumn) => {
    const state = get();
    if (state.variantColumn === variantColumn) return;
    const selectionWasEmpty = state.selectedWells === null;
    set({
      variantColumn,
      variantSelectionExplicit: true,
      validationErrors: [],
      wellSelectionOccupants: null,
    });
    get().setSelectedWells(null);
    // Like the sheet, a column names a different expected-row set even when
    // there is no well declaration left for `setSelectedWells` to invalidate.
    if (selectionWasEmpty) get().clearResults();
  },
  setJanusSettings: (janusSettings: JanusExportSettings) => {
    saveJanusSettings(janusSettings);
    set({ janusSettings });
  },
  // Set by the mapping panel (JanusMappingPanel) after a successful manual
  // export, the only writer of the instrument mapping now that analyze does
  // not write it automatically. Feeds the same "done" signal and drawer/
  // inspector displays that used to read the automatic file.
  setJanusMappingAutosave: (janusMappingAutosave) => set({ janusMappingAutosave }),
  // Every analyze/demux call sends this as the amplicon reference, so a swap
  // invalidates a completed run's verdicts (same reasoning as setInputDir).
  setReferencePath: (referencePath) => {
    const changed = get().referencePath !== referencePath;
    set({ referencePath, validationErrors: [] });
    void get().refreshAnalyzeCdsCandidates(referencePath);
    if (changed) get().clearResults();
  },
  // Just where the export lands, not what was analyzed. Does not invalidate
  // a completed run's outputs.
  setOutputPath: (outputPath) => set({ outputPath, validationErrors: [] }),
  // Which wells the campaign occupies. Sent as `selected_wells` and decides
  // where every variant lands, so a change invalidates a completed run's
  // per-well verdicts the same way swapping an input file does.
  setSelectedWells: (selectedWells) => {
    const before = get().selectedWells;
    const changed =
      (before === null) !== (selectedWells === null) ||
      (before !== null &&
        selectedWells !== null &&
        (before.length !== selectedWells.length ||
          before.some((well, i) => well !== selectedWells[i])));
    set({ selectedWells });
    if (changed) get().clearResults();
  },
  // How many things the variant list puts on the plate, as the draft RPC read
  // it. Display state on its own; `selectCanRun` is what makes it matter, by
  // holding the run when the declared wells cannot seat them all.
  setWellSelectionOccupants: (wellSelectionOccupants) =>
    set({ wellSelectionOccupants }),
  // Sent as `wt_placement` to every analyze call; changing it changes which
  // wells are treated as controls and therefore invalidates finished verdicts.
  setWtPlacement: (wtPlacement) => {
    if (get().wtPlacement === wtPlacement) return;
    set({ wtPlacement });
    get().clearResults();
  },
  setWtWell: (wtWell) => set({ wtWell }),
  // Migration only, and never an input: the run does not read this file, it is
  // compared against the computed layout. Setting it therefore invalidates
  // nothing.
  setLegacySampleMapPath: (legacySampleMapPath) => set({ legacySampleMapPath }),
  setProjectPath: (projectPath) => set({ projectPath }),
  // mode/cdsStart/cdsEnd/minFileSizeKb/minFilteredDepth/manyCutoff/
  // maxConsensusNFraction and rawRunParams are all sent verbatim as
  // analyze/demux RPC params, so a change here invalidates a completed run the
  // same way the file setters above do.
  setParams: (params) => {
    const state = get();
    const nextRawRunParams =
      params.rawRunParams != null
        ? { ...state.rawRunParams, ...params.rawRunParams }
        : state.rawRunParams;
    const changed =
      (params.mode !== undefined && params.mode !== state.mode) ||
      (params.ingestMode !== undefined && params.ingestMode !== state.ingestMode) ||
      (params.inputMode !== undefined && params.inputMode !== state.inputMode) ||
      (params.cdsStart !== undefined && params.cdsStart !== state.cdsStart) ||
      (params.cdsEnd !== undefined && params.cdsEnd !== state.cdsEnd) ||
      (params.minFileSizeKb !== undefined && params.minFileSizeKb !== state.minFileSizeKb) ||
      (params.minFilteredDepth !== undefined &&
        params.minFilteredDepth !== state.minFilteredDepth) ||
      (params.manyCutoff !== undefined && params.manyCutoff !== state.manyCutoff) ||
      (params.maxConsensusNFraction !== undefined &&
        params.maxConsensusNFraction !== state.maxConsensusNFraction) ||
      JSON.stringify(nextRawRunParams) !== JSON.stringify(state.rawRunParams);
    set({
      mode: params.mode ?? state.mode,
      ingestMode: params.ingestMode ?? state.ingestMode,
      inputMode: params.inputMode ?? state.inputMode,
      rawRunParams: nextRawRunParams,
      cdsStart: params.cdsStart ?? state.cdsStart,
      cdsEnd: params.cdsEnd ?? state.cdsEnd,
      minFileSizeKb: params.minFileSizeKb ?? state.minFileSizeKb,
      minFilteredDepth: params.minFilteredDepth ?? state.minFilteredDepth,
      manyCutoff: params.manyCutoff ?? state.manyCutoff,
      maxConsensusNFraction: params.maxConsensusNFraction ?? state.maxConsensusNFraction,
      validationErrors: [],
      // The counts describe the barcode workbook the last validation read, and
      // customBarcodesPath lives in rawRunParams, so any change here can mean a
      // different file. Cleared with the errors rather than left to describe a
      // workbook nobody picked any more.
      barcodeAxisCounts: null,
    });
    if (changed) get().clearResults();
  },
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
          target_length: rawRunParams.targetLength ?? undefined,
          length_tolerance_bp: rawRunParams.lengthToleranceBp,
          auto_detect_length: rawRunParams.targetLength === null,
          normalize_headers: rawRunParams.normalizeHeaders,
        },
        MAME_DEMUX_RPC_TIMEOUT_MS,
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
  // Ask the sidecar about the expected workbook alone, without the rest of a
  // validation.
  //
  // A file pick is the path that let the 2026-08-04 incident through, and it is
  // the moment the operator can still act on the answer. Running the full
  // `validate_inputs` here would report every input not chosen yet ("input_dir
  // is required") as an error over a file the user just picked correctly, and
  // those errors feed `selectCanRun`. `check_plate_order` opens the one workbook
  // instead, which is the same cost the restore path already pays.
  //
  // It answers without a severity, so grade it the way the sidecar would.
  checkExpectedPlateOrder: async (expectedPath: string) => {
    if (!expectedPath) {
      set({ plateOrderFinding: null });
      return;
    }
    let report: PlateOrderReport | null = null;
    try {
      const raw = await sendRequest<unknown>("check_plate_order", { path: expectedPath }, 30_000);
      // An older sidecar does not know the method and a test double answers
      // undefined. Reading fields before the shape is confirmed would turn a
      // missing feature into a broken file picker.
      if (raw && typeof raw === "object" && "comparable" in raw) {
        report = raw as PlateOrderReport;
      }
    } catch {
      // A check that cannot run is not a finding. Staying silent leaves the
      // validate/analyze path to say it, and inventing a block here would
      // strand every operator on an older sidecar.
      return;
    }
    // Race guard: the operator may have picked another file mid-flight.
    if (!report || get().expectedPath !== expectedPath) return;
    if (!isPlateOrderReportable(report)) {
      set({ plateOrderFinding: null });
      return;
    }
    // Blocking, and stored before any validation runs: `selectCanRun` reads this
    // field directly, so picking the workbook is enough to hold the run. Which
    // of the workbook's two plates was pipetted is written nowhere on this
    // screen, so there is no input that answers it and no grade below blocking.
    set({ plateOrderFinding: { ...report, severity: "blocking" } });
  },
  validateInputs: async () => {
    set({ isValidating: true, validationErrors: [] });
    try {
      const state = get();
      const result = await sendRequest<ValidationResult>("validate_inputs", {
        ...analyzeInputParams(state),
        // Raw-run guard in the backend validate_inputs needs the barcodes xlsx
        // to recognise a configured raw MinKNOW run folder; empty in non-raw mode.
        custom_barcodes_xlsx: state.rawRunParams.customBarcodesPath,
      });
      set({
        validationErrors: result.errors,
        // Absent key = nothing to report, which has to clear a previous finding.
        plateOrderFinding: result.plate_order ?? null,
        // Same absent-clears rule: a project whose sample map was deleted
        // between validations must not keep showing the old answer.
        legacySampleMapFinding: result.legacy_sample_map ?? null,
        // Same rule: absent means no workbook was read this time, so a line
        // left over from a previous file would describe the wrong one.
        barcodeAxisCounts: result.barcode_axes ?? null,
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
  // Shared raw_run analyze body. The backend `analyze` handler accepts a raw
  // MinKNOW run folder directly (input_dir contains fastq_pass/): it internally
  // demuxes (progress stage='demux', mapped to 0..50) then analyzes
  // (stage='analyze', 50..100) in ONE round-trip and returns the normal analyze
  // response plus assigned_reads/wells_with_reads. nativeBarcodes threads the
  // per-NB selection: null/[] -> single pool, non-empty -> per-NB demux.
  // analyzePhase starts 'demux' here; the progress subscription flips it to
  // 'analyze' off the stage field. Happy path only; callers (runAnalysis /
  // confirmNativeBarcodeSelection) own the try/catch that resets isAnalyzing
  // and surfaces validationErrors.
  _demuxAndAnalyze: async (nativeBarcodes: string[] | null) => {
    const state = get();
    const { rawRunParams } = state;

    set({
      analyzeProgress: 0,
      analyzePhase: "demux",
      analyzeMessage: "Demuxing raw MinKNOW run",
    });
    const targetRoundId = useRoundStore.getState().active_round_id;
    const runId = createAnalyzeRunId();

    const result = await sendRequest<AnalyzeResult>(
      "analyze",
      {
        ...analyzeInputParams(state),
        output: joinPathSlice(state.outputPath, defaultMameExportFilename({ referencePath: state.referencePath, inputDir: state.inputDir, verdictCount: 0 })),
        mode: state.mode,
        ingest_mode: "barcode",
        janus_settings: toRpcParams(state.janusSettings),
        // Raw-run demux knobs folded into analyze. `reference` above is reused
        // server-side as reference_fasta.
        custom_barcodes_xlsx: rawRunParams.customBarcodesPath,
        native_barcodes: nativeBarcodes,
        coverage_fraction: rawRunParams.coverageFraction,
        edit_dist_ratio: rawRunParams.editDistRatio,
        chimera_split: rawRunParams.chimeraSplit,
        demux_output_dir: deriveDemuxOutputDir(state.outputPath),
        mapq_threshold: 25,
        trim_flank_bp: 30,
      },
      MAME_RAWRUN_RPC_TIMEOUT_MS,
    );
    persistRoundAnalyzeEvidence(targetRoundId, runId, result);

    get().setVerdicts(result.verdicts);
    get().setReplicates(result.replicates);
    get().setSummary(result.summary);
    get().setAnalyzeYield(pickAnalyzeYield(result));
    get().setLayoutProvenance(result.layout_provenance ?? null);
    get().setMappingIntegrity(result.mapping_integrity ?? null);
    get().setStaleUnits(result.stale_units ?? null);
    get().setOffLayoutRecords(result.off_layout_records ?? null);
    get().setRunQuality(result.run_quality ?? null);
    get().setContamination(result.contamination ?? null);
    // Which reference this run actually read. Only the raw-run path resolves
    // one, so this is the branch that can carry a real value; `?? null` still
    // covers a sidecar older than the field, which must read as "no run
    // reported one" rather than as "the whole file was used".
    get().setReferenceResolution(result.reference_resolution ?? null);
    get().setDemuxResume(result.demux_resume ?? null);
    // Store the folder only (outputPath is now a folder); lastExportPath tracks the full path.
    const outDir = (() => {
      const p = result.output_path.replace(/\\/g, "/");
      const i = p.lastIndexOf("/");
      return i >= 0 ? result.output_path.slice(0, i) : result.output_path;
    })();
    get().setOutputPath(outDir);
    get().setDistributionStats(result.distribution_stats ?? null);
    // What this run judged its wells against, so the Confidence metric popups
    // can state a threshold instead of a literal. `?? null` covers a sidecar
    // older than the field, which must read as unknown.
    get().setCompareParams(result.compare_params ?? null);
    // The run wrote (or could not write) its pick list. Kept so the result
    // view can state it; swallowing it leaves the operator looking for a file
    // that was never created. The instrument mapping has no autosave counterpart
    // here: `janusMappingAutosave` was already cleared by this run's
    // `clearResults()` and stays null until the operator exports one from
    // `JanusMappingPanel`.
    set({ janusAutosave: result.janus_autosave ?? null });
    // Persist the FULL analyze response AS-IS (sibling result file) once on
    // success, so restart can replay it into the sidecar + restore the 2.2
    // review view. Awaited so an immediate app-close does not lose it. Failure
    // must not break the in-memory flow (best-effort).
    try {
      await writeMameResultSnapshot(get().projectPath, result);
    } catch (err) {
      console.warn("[inputSlice] persist analyze result failed:", err);
    }
    await get().loadPlateData();
    // A8: auto-load run health after analysis completes (non-blocking on failure)
    void get().loadRunHealth();
    set({
      isAnalyzing: false,
      analyzeProgress: 100,
      analyzeMessage: "Analysis complete",
      analyzeCurrent: null,
      analyzeTotal: null,
      analyzeStage: null,
      analyzeStartedAt: null,
      analyzeDurationMs: elapsedSince(get().analyzeStartedAt),
      analyzePhase: null,
    });
  },
  runAnalysis: async () => {
    // No plate-order gate here any more. The operator names the sheet and the
    // column the variant list is read from (v0.15.6), so a disagreement between
    // two sheets of one workbook is reported by PlateOrderNotice and left to
    // them: refusing would be the program overruling a statement it asked for.
    set({
      isAnalyzing: true,
      analyzeProgress: 0,
      analyzeMessage: "Starting analysis",
      analyzeCurrent: null,
      analyzeTotal: null,
      analyzeStage: null,
      analyzeStartedAt: Date.now(),
      // A new run invalidates the previous run's duration, so the completion
      // popup keyed on null -> number can fire again.
      analyzeDurationMs: null,
      analyzePhase: null,
      validationErrors: [],
    });
    try {
      const state = get();

      if (state.inputMode === "raw_run") {
        const inputErrors = getDemuxInputErrors(state);
        if (inputErrors.length > 0) {
          throw new Error(inputErrors.join("\n"));
        }

        // Detect native barcodes FIRST (after the input-error guard, before
        // demux). total_count > 1 pauses for per-NB selection via the dialog.
        set({ isDetectingBarcodes: true });
        const detect = await sendRequest<DetectNativeBarcodesResult>(
          "mame.detect_native_barcodes",
          { minknow_run_dir: state.inputDir },
        );

        if (detect.total_count > 1) {
          // Pause and surface the confirm dialog. Leave isAnalyzing true so the
          // UI knows an analysis is pending; the dialog drives the next step.
          // The count is recorded here, before the selection exists: it is what
          // the folder holds, and the notice compares the two.
          set({
            detectedNativeBarcodes: detect.native_barcodes,
            detectedBarcodeCount: detect.total_count,
            isDetectingBarcodes: false,
          });
          return;
        }

        // Single pool (0 or 1 native barcode): proceed exactly as before.
        // `[]` records that the run covers one plate, which is not the same
        // statement as null (no raw-run selection applies at all).
        set({
          isDetectingBarcodes: false,
          detectedBarcodeCount: detect.total_count,
          selectedNativeBarcodes: [],
        });
        await get()._demuxAndAnalyze(null);
        return;
      }

      // Non-raw_run modes: analyze the inputDir directly (current behaviour).
      const targetRoundId = useRoundStore.getState().active_round_id;
      const runId = createAnalyzeRunId();
      const result = await sendRequest<AnalyzeResult>(
        "analyze",
        {
          ...analyzeInputParams(state),
          output: joinPathSlice(state.outputPath, defaultMameExportFilename({ referencePath: state.referencePath, inputDir: state.inputDir, verdictCount: 0 })),
          mode: state.mode,
          ingest_mode: state.ingestMode,
          // The sidecar writes the pick list at the end of every run
          // (`_autosave_picks`, forced to legacy5), which honours dest_layout
          // and include_verdicts/include_fallback from these settings but
          // never the instrument fields; the instrument mapping is written
          // only by a manual export from JanusMappingPanel.
          janus_settings: toRpcParams(state.janusSettings),
        },
        MAME_ANALYZE_RPC_TIMEOUT_MS,
      );
      persistRoundAnalyzeEvidence(targetRoundId, runId, result);

      get().setVerdicts(result.verdicts);
      get().setReplicates(result.replicates);
      get().setSummary(result.summary);
      get().setAnalyzeYield(pickAnalyzeYield(result));
      get().setLayoutProvenance(result.layout_provenance ?? null);
      get().setMappingIntegrity(result.mapping_integrity ?? null);
      get().setStaleUnits(result.stale_units ?? null);
      get().setOffLayoutRecords(result.off_layout_records ?? null);
    get().setRunQuality(result.run_quality ?? null);
      get().setContamination(result.contamination ?? null);
      // See the raw-run branch. This path never resolves a reference (the
      // sidecar only does it for a MinKNOW run folder), so the value here is
      // always null; written anyway so both branches state every result field
      // and neither can be read as forgetting one.
      get().setReferenceResolution(result.reference_resolution ?? null);
      get().setDemuxResume(result.demux_resume ?? null);
      const outDir = (() => {
        const p = result.output_path.replace(/\\/g, "/");
        const i = p.lastIndexOf("/");
        return i >= 0 ? result.output_path.slice(0, i) : result.output_path;
      })();
      get().setOutputPath(outDir);
      get().setDistributionStats(result.distribution_stats ?? null);
      get().setCompareParams(result.compare_params ?? null);
      // See the non-raw-run branch above: no `janus_mapping_autosave` from the
      // sidecar to read here either, so `janusMappingAutosave` stays whatever
      // this run's `clearResults()` already left it (null).
      set({ janusAutosave: result.janus_autosave ?? null });
      try {
        await writeMameResultSnapshot(get().projectPath, result);
      } catch (err) {
        console.warn("[inputSlice] persist analyze result failed:", err);
      }
      await get().loadPlateData();
      void get().loadRunHealth();
      set({
        isAnalyzing: false,
        analyzeProgress: 100,
        analyzeMessage: "Analysis complete",
        analyzeCurrent: null,
        analyzeTotal: null,
        analyzeStage: null,
        analyzeStartedAt: null,
        analyzeDurationMs: elapsedSince(get().analyzeStartedAt),
        analyzePhase: null,
      });
    } catch (error) {
      set({
        isAnalyzing: false,
        isDetectingBarcodes: false,
        analyzeMessage: "Analysis failed",
        analyzeStartedAt: null,
        // A failed run has no duration to report; leaving a stale value here
        // would surface a completion popup for a run that never completed.
        analyzeDurationMs: null,
        analyzePhase: null,
        validationErrors: [formatError(error)],
      });
    }
  },
  confirmNativeBarcodeSelection: async (selected: string[]) => {
    // Two namespaces, one selection. The RPC needs the MinKNOW directory names
    // (`barcode06`), because the demux reads `fastq_pass/<name>/`
    // (kuma_core/mame/ingest/run_pipeline.py::_collect_per_nb_fastq). Every
    // record that comes back is stamped with the OUTPUT directory name
    // (`sort_barcode06`), so the axis the results are read on is the sort form
    // (combinatorial_demux.py `_nb_to_sort_barcode_name`, fasta_parser.py
    // `load_barcode_directory`). The mapping is taken from the detect payload
    // rather than recomputed here, so there is no second copy of the naming
    // rule to drift; a name the payload does not carry is stored as-is.
    const detected = get().detectedNativeBarcodes ?? [];
    const sortNames = selected.map(
      (name) => detected.find((nb) => nb.name === name)?.sort_barcode_name ?? name,
    );
    // Empty selection = pooled: one plate, all reads in one pool. The RPC takes
    // null for that (an empty list is rejected by the Pydantic validator on
    // `native_barcodes`), while the store keeps `[]` to distinguish "pooled"
    // from "no raw-run selection applies".
    const requested = selected.length > 0 ? selected : null;
    // Close the dialog and resume per-NB demux+analyze with the selection.
    set({
      detectedNativeBarcodes: null,
      isDetectingBarcodes: false,
      selectedNativeBarcodes: sortNames,
    });
    try {
      await get()._demuxAndAnalyze(requested);
    } catch (error) {
      set({
        isAnalyzing: false,
        analyzeMessage: "Analysis failed",
        analyzeStartedAt: null,
        analyzeDurationMs: null,
        analyzePhase: null,
        validationErrors: [formatError(error)],
      });
    }
  },
  cancelNativeBarcodeSelection: () => {
    set({
      detectedNativeBarcodes: null,
      // Cancel aborts the analysis, so no run is going to be scored on the axis
      // this detect found. Leaving the count behind would have the notice
      // describe a run that never started.
      detectedBarcodeCount: null,
      isAnalyzing: false,
      isDetectingBarcodes: false,
      analyzeMessage: "",
      analyzeStartedAt: null,
      analyzeDurationMs: null,
      analyzePhase: null,
    });
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
      analyzeStage: null,
      analyzeStartedAt: null,
      // A cancelled run reports no duration. `summary` alone cannot express
      // this: cancelling a re-run leaves the previous run's summary in place.
      analyzeDurationMs: null,
      analyzePhase: null,
    });
  },
  resetInput: () => set({ ...mameInputInitialState }),
});
