import type { SortingState, Updater } from "@tanstack/react-table";
import type { BuildEvolveproCompletionRecord } from "@/lib/mame/buildEvolveproFormStorage";
import type { RestoredResultProvenance } from "@/lib/mame/resultProvenance";
export type { MamePhase, PhaseSlice } from "./slices/phaseSlice";
import type {
  AmpliconLengthEstimate,
  AnalyzeSummary,
  AnalyzeYield,
  CompareParams,
  DistributionStats,
  BarcodeAxisCounts,
  DemuxAndFilterResult,
  JanusAutosaveResult,
  JanusExportSettings,
  LayoutProvenance,
  LegacySampleMapFinding,
  MappingIntegrity,
  ContaminationReport,
  OffLayoutRecords,
  PlateOrderFinding,
  ReplicateResult,
  RunHealthData,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";
import type { CdsCandidate } from "@/lib/sequence/autoDetectCds";
import type { NativeBarcodeUsage } from "@/types/mame/detect_native_barcodes";
import type { VariantSourceInfo } from "@/types/mame/barcode_package";
import type { WellLayout } from "@/types/mame/well_layout";

export type InputMode = "consensus" | "sorted_barcode" | "raw_run";

export interface RawRunParams {
  customBarcodesPath: string;
  sequencingSummaryPath: string;
  minQscore: number;
  lengthMin: number;
  lengthMax: number;
  // R6.5: amplicon length auto-detection
  targetLength: number | null;       // null → auto-detect
  lengthToleranceBp: number;         // ± window around targetLength
  // R6.5: header normalization
  normalizeHeaders: boolean;         // write >{well} FASTA headers
  // PR-A: combinatorial demux advanced params
  coverageFraction: number;          // min fraction of ref covered [0.5, 1.0], default 0.98
  editDistRatio: number;             // max edit dist fraction of barcode prefix [0, 0.5], default 0.25
  chimeraSplit: boolean;             // evaluate all alignment hits per read, default true
}

export interface InputSlice {
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  /**
   * Wells this campaign occupies, in plate order, or null for "the leading
   * ones". Null is the default and produces exactly the layout every run
   * produced before this field existed, so an operator who never opens the
   * grid sees no change at all.
   *
   * A campaign smaller than the plate leaves wells empty and no input file
   * says which. Declaring them is what lets a read arriving from an empty well
   * be reported as a read from an empty well rather than scored as whatever
   * the draft happened to place there.
   */
  selectedWells: string[] | null;
  /**
   * How many things the current variant list puts on the plate (variants plus
   * the one WT control), or null when nothing has read it yet.
   *
   * Written by `WellSelectionPanel` off the same `build_well_layout` RPC that
   * draws the grid, and read by `selectCanRun`: a selection shorter than this
   * is refused by the sidecar, so the button has to be held before the run
   * starts rather than after. Cleared with every input that changes which rows
   * are read, because a count from the previous workbook would gate the next
   * one.
   */
  wellSelectionOccupants: number | null;
  /**
   * An existing project's `sample_map_template.xlsx`, named by its schema-1
   * `mame_context.json`. NOT an input: the sample map was removed because it
   * stated the plate a second time and nothing kept the two in step. Sent to
   * `validate_inputs` so the backend can compare it against the computed
   * layout and name the wells where they disagree.
   */
  legacySampleMapPath: string | null;
  // Project root, bridged from useKumaProject() context via useMameAutosave so
  // analyze-result persistence (resultSnapshot.ts) can write from the slice,
  // which has no React context access. null/scratch -> no result file written.
  projectPath: string | null;
  mode: "amplicon" | "plasmid";
  ingestMode: "barcode" | "amplicon";
  inputMode: InputMode;
  rawRunParams: RawRunParams;
  cdsStart: number;
  cdsEnd: number;
  minFileSizeKb: number;
  minFilteredDepth: number;
  manyCutoff: number;
  maxConsensusNFraction: number;
  validationErrors: string[];
  isValidating: boolean;
  isAnalyzing: boolean;
  isDemuxing: boolean;
  analyzeProgress: number;
  analyzeMessage: string;
  analyzeCurrent: number | null;
  analyzeTotal: number | null;
  analyzeStage: string | null;
  analyzeStartedAt: number | null;
  // Wall-clock duration of the last analyze run that actually produced a
  // response, derived from `analyzeStartedAt` at the moment that response was
  // applied. `analyzeStartedAt` is cleared in the same `set()` that ends a run,
  // so the elapsed time cannot be recovered afterwards; and only the success
  // path writes this, which is what separates "finished" from "cancelled"
  // (cancel leaves a previous run's `summary` in place). null = no completed
  // run since the current one started.
  analyzeDurationMs: number | null;
  analyzePhase: "demux" | "analyze" | null;
  demuxProgress: number;
  demuxMessage: string;
  demuxResult: DemuxAndFilterResult | null;
  distributionStats: DistributionStats | null;
  ampliconLengthEstimate: AmpliconLengthEstimate | null;
  // Native barcode detect -> confirm -> per-NB demux flow (raw_run mode).
  // null = no dialog open; non-null = show the confirm dialog with these rows.
  detectedNativeBarcodes: NativeBarcodeUsage[] | null;
  isDetectingBarcodes: boolean;
  /**
   * The replicate axis the current results were produced on, as
   * `native_barcode` (`sort_barcodeNN`) names, NOT the MinKNOW directory names
   * (`barcodeNN`) the dialog checks off.
   *
   * The two namespaces are different and the records use the sort form: the
   * demux writes one output directory per native barcode named by
   * `_nb_to_sort_barcode_name` (kuma_core/mame/ingest/combinatorial_demux.py),
   * and `load_barcode_directory` takes each record's `native_barcode` from that
   * directory name (kuma_core/mame/ingest/fasta_parser.py). Storing the
   * MinKNOW form here would make every well look absent from every plate.
   *
   * `[]` = pooled: one plate, all reads in one pool. null = no raw-run
   * selection applies (consensus-directory run, or nothing run yet), which is
   * what makes `missing_replicate` undecidable.
   *
   * Cleared by `clearResults`, together with the verdicts it describes: after
   * an input change the previous run's replicate axis describes nothing on
   * screen.
   */
  selectedNativeBarcodes: string[] | null;
  /**
   * How many native barcodes the detect step counted in the run folder
   * (`detect.total_count`), regardless of how many were then selected. Kept so
   * the review screen can say that a run covered fewer replicates than the
   * folder holds. Cleared by `clearResults` for the same reason as above.
   */
  detectedBarcodeCount: number | null;
  // Well->sample mapping passed to analyze as the highest-priority source.
  // v0.15.6 removed the UI that built one (nobody checked 96 rows by hand, and
  // analyze assigns wells on its own regardless), so this is non-null only
  // when restored from a project saved before that. The `well_layout` RPC
  // param stays: it is the contract, and it still outranks the sample map.
  wellLayout: WellLayout | null;
  // Does the chosen expected workbook agree with its own primer plate sheet?
  // null = nothing to report (agrees, not comparable, not checked yet, or the
  // operator named the sheet and column themselves). Stated, never gated: since
  // v0.15.6 the operator points at the list to read, so the program has no
  // ground left to refuse the run.
  plateOrderFinding: PlateOrderFinding | null;
  // Does an existing project's pre-removal `sample_map_template.xlsx` agree
  // with the layout this run would use? null = no such file, or not validated
  // yet. `"differs"` is also an entry in `validationErrors` and blocks there;
  // `"matches"` is announced once so the operator can delete the file.
  legacySampleMapFinding: LegacySampleMapFinding | null;
  // What the barcode workbook the last validation read actually contains: seeds
  // per axis and the wells they can name. null = no workbook, unreadable, or
  // not validated yet. Display only, never an input: the axis roles and the
  // fill order are properties of how the barcodes were prepared.
  barcodeAxisCounts: BarcodeAxisCounts | null;
  // What the picked variant list offers (sheets, headers, the column the
  // backend would choose). null = not inspected, or the sidecar could not.
  variantSourceInfo: VariantSourceInfo | null;
  // Sheet and column to read the variant list with. null = let the backend
  // decide, which is the pre-v0.15.6 behaviour.
  variantSheet: string | null;
  variantColumn: string | null;
  // True once the operator changed either of the two above by hand. Their
  // statement about which rows to read outranks any disagreement the program
  // spots between two sheets of the same workbook.
  variantSelectionExplicit: boolean;
  // Janus policy the analyze run writes its automatic pick list with, shared
  // with the mapping panel so both files describe the same plate.
  janusSettings: JanusExportSettings;
  // What became of that automatic pick list on the last run. null = no run yet.
  janusAutosave: JanusAutosaveResult | null;
  // What became of the instrument mapping. Unlike janusAutosave this is never
  // written by analyze: only a manual export from the step 3 mapping panel
  // sets it (setJanusMappingAutosave), because a robot worklist states a deck
  // and a liquid class that describe the room at export time, not at analyze
  // time. null = nothing exported yet for this run's inputs.
  janusMappingAutosave: JanusAutosaveResult | null;
  inspectVariantSource: (path: string) => Promise<void>;
  setVariantSheet: (sheet: string | null) => void;
  setVariantColumn: (column: string | null) => void;
  setJanusSettings: (settings: JanusExportSettings) => void;
  setJanusMappingAutosave: (result: JanusAutosaveResult | null) => void;
  setInputDir: (path: string) => void;
  setExpectedPath: (path: string) => void;
  setReferencePath: (path: string) => void;
  setOutputPath: (path: string) => void;
  setSelectedWells: (wells: string[] | null) => void;
  setWellSelectionOccupants: (count: number | null) => void;
  setLegacySampleMapPath: (path: string | null) => void;
  setProjectPath: (path: string | null) => void;
  setParams: (
    params: Partial<{
      mode: "amplicon" | "plasmid";
      ingestMode: "barcode" | "amplicon";
      inputMode: InputMode;
      rawRunParams: Partial<RawRunParams>;
      cdsStart: number;
      cdsEnd: number;
      minFileSizeKb: number;
      minFilteredDepth: number;
      manyCutoff: number;
      maxConsensusNFraction: number;
    }>,
  ) => void;
  setValidationErrors: (errors: string[]) => void;
  setIsAnalyzing: (value: boolean) => void;
  setIsDemuxing: (value: boolean) => void;
  setAnalyzeProgress: (value: number) => void;
  setAnalyzeMessage: (message: string) => void;
  setDemuxProgress: (value: number) => void;
  setDemuxMessage: (message: string) => void;
  setDemuxResult: (result: DemuxAndFilterResult | null) => void;
  setDistributionStats: (stats: DistributionStats | null) => void;
  setAmpliconLengthEstimate: (estimate: AmpliconLengthEstimate | null) => void;
  // CDS candidate dropdown (BarcodeSetupPanel)
  cdsCandidates: CdsCandidate[];
  selectedCdsIndex: number;
  setCdsCandidates: (candidates: CdsCandidate[]) => void;
  setSelectedCdsIndex: (index: number) => void;
  // CDS candidate dropdown (ParameterPanel / analyze phase). Populated by
  // mame.ingest.parse_reference when the reference path changes; empty for
  // plain FASTA, in which case ParameterPanel falls back to manual numeric
  // entry for cds_start / cds_end.
  analyzeCdsCandidates: CdsCandidate[];
  selectedAnalyzeCdsIndex: number | null;
  setAnalyzeCdsCandidates: (candidates: CdsCandidate[]) => void;
  setSelectedAnalyzeCdsIndex: (index: number | null) => void;
  refreshAnalyzeCdsCandidates: (referencePath: string) => Promise<void>;
  // Shared file paths between KURO and MAME. KURO loadSequence/loadEvolveproCsv
  // dual-write here so MAME panels can prefill without manual re-Browse.
  sharedFastaPath: string | null;
  sharedEvolveproCsvPath: string | null;
  setSharedFastaPath: (path: string | null) => void;
  setSharedEvolveproCsvPath: (path: string | null) => void;
  // Bumped on resetMameAll so component-local form state (BarcodeSetupPanel)
  // can subscribe and re-initialise via a useEffect dependency.
  resetEpoch: number;
  bumpResetEpoch: () => void;
  validateInputs: () => Promise<void>;
  // Check one expected workbook against its own plate sheet and store the graded
  // result. Called right after the operator picks the file, before any other
  // input is necessarily chosen. Silent when the check cannot run.
  checkExpectedPlateOrder: (expectedPath: string) => Promise<void>;
  runDemuxAndFilter: () => Promise<void>;
  runAnalysis: () => Promise<void>;
  cancelAnalysis: () => Promise<void>;
  // Internal shared raw_run helper: run_combinatorial_demux (threading
  // native_barcodes: null -> single pool, non-empty -> per-NB) then analyze +
  // result handling. Not part of the public detect->confirm contract; called by
  // runAnalysis and confirmNativeBarcodeSelection.
  _demuxAndAnalyze: (nativeBarcodes: string[] | null) => Promise<void>;
  // Resume per-NB demux+analyze with the user-selected MinKNOW barcode dir
  // names (e.g. "barcode06"); closes the confirm dialog first.
  confirmNativeBarcodeSelection: (selected: string[]) => Promise<void>;
  // Close the confirm dialog and abort the pending analysis.
  cancelNativeBarcodeSelection: () => void;
  resetInput: () => void;
}

export interface AnalysisSlice {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  summary: AnalyzeSummary | null;
  /**
   * Demux yield carried by the last analyze response, or null when the response
   * reported none (consensus-dir mode). Retained so a run that finished with 0
   * verdicts can explain itself with backend-reported counts instead of
   * guessed ones.
   */
  analyzeYield: AnalyzeYield | null;
  /**
   * Which well->sample source the last analyze response scored against, or
   * null when no run has completed since the last reset. See
   * `LayoutProvenance` (`@/types/mame/models`) for why this must not be
   * silently promoted into an explicit well_layout on restore.
   */
  layoutProvenance: LayoutProvenance | null;
  /**
   * Whole-run mapping sanity check carried by the last analyze response, or
   * null when no run has completed since the last reset.
   */
  mappingIntegrity: MappingIntegrity | null;
  /**
   * The thresholds the last analyze response says it judged its wells against.
   * Read by the Confidence metric popups, which state what a number was
   * compared to; every one of those thresholds has a backend default that
   * applies when the caller omits it (`min_read_count` is omitted on every
   * run), so the store's own input fields cannot answer the question and a
   * literal in the TSX would silently drift from the engine.
   *
   * null = no run has completed since the last reset, OR the results on screen
   * were restored from a snapshot written before the sidecar reported this.
   * Both cases must render as "unknown", never as a default value.
   */
  compareParams: CompareParams | null;
  /**
   * Reads that arrived from wells the run layout does not name, or null when no
   * run has completed since the last reset. Reported, never a gate: the same
   * counts appear for a well the operator declared empty and for barcode
   * crosstalk, and nothing in the number separates the two.
   */
  offLayoutRecords: OffLayoutRecords | null;
  /**
   * What the demux matrix said about reads outside the campaign, or null when
   * no run has completed since the last reset AND when the completed run could
   * not measure it (a consensus-dir run never demuxes, so it has no matrix).
   * The two are deliberately the same value here: neither is a clean plate, and
   * the panel says "not measured" for both.
   */
  contamination: ContaminationReport | null;
  /**
   * Set when the results on screen were restored from a snapshot this build did
   * not write, so the review screen can say whose engine produced them. Null
   * for a run made in this session and for a same-version restore, which is the
   * case that must look exactly as it did before.
   */
  restoredResultProvenance: RestoredResultProvenance | null;
  plateFilter: string;
  searchQuery: string;
  sorting: SortingState;
  showExport: boolean;
  wells: WellEntry[];
  selectedWell: WellEntry | null;
  runHealth: RunHealthData | null;
  buildEvolveproCompletion: BuildEvolveproCompletionRecord | null;
  setVerdicts: (verdicts: VerdictRecord[]) => void;
  setReplicates: (replicates: ReplicateResult[]) => void;
  setSummary: (summary: AnalyzeSummary | null) => void;
  setAnalyzeYield: (analyzeYield: AnalyzeYield | null) => void;
  setLayoutProvenance: (layoutProvenance: LayoutProvenance | null) => void;
  setMappingIntegrity: (mappingIntegrity: MappingIntegrity | null) => void;
  setCompareParams: (compareParams: CompareParams | null) => void;
  setOffLayoutRecords: (offLayoutRecords: OffLayoutRecords | null) => void;
  setContamination: (contamination: ContaminationReport | null) => void;
  setRestoredResultProvenance: (
    provenance: RestoredResultProvenance | null,
  ) => void;
  setPlateFilter: (filter: string) => void;
  setSearchQuery: (query: string) => void;
  setSorting: (updater: Updater<SortingState>) => void;
  openExport: () => void;
  closeExport: () => void;
  setWells: (wells: WellEntry[]) => void;
  setSelectedWell: (well: WellEntry | null) => void;
  setBuildEvolveproCompletion: (
    completion: BuildEvolveproCompletionRecord | null,
  ) => void;
  loadPlateData: () => Promise<void>;
  loadRunHealth: () => Promise<void>;
  clearResults: () => void;
  loadSampleData: () => Promise<void>;
  resetAnalysis: () => void;
  // Sample-data prefill bridge: analysisSlice publishes resolved sample paths
  // (fasta + barcode seeds xlsx); BarcodeSetupPanel reads + consumes them so
  // the user does not have to re-click Browse for the demo files.
  mameSamplePrefill: { fastaPath: string; barcodeSeedsPath: string } | null;
  consumeMameSamplePrefill: () => void;
}

export interface ExportSlice {
  lastExportPath: string | null;
  lastExportAt: string | null;
  isExporting: boolean;
  exportError: string | null;
  exportExcel: (path: string) => Promise<void>;
  resetExport: () => void;
}
