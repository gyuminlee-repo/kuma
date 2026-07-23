import type { SortingState, Updater } from "@tanstack/react-table";
export type { MamePhase, PhaseSlice } from "./slices/phaseSlice";
import type {
  AmpliconLengthEstimate,
  AnalyzeSummary,
  DistributionStats,
  DemuxAndFilterResult,
  ReplicateResult,
  RunHealthData,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";
import type { CdsCandidate } from "@/lib/sequence/autoDetectCds";
import type { NativeBarcodeUsage } from "@/types/mame/detect_native_barcodes";
import type { WellLayout, WellLayoutRow } from "@/types/mame/well_layout";

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
  sampleMapPath: string;
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
  // Well-layout confirm flow: null = not started; non-null = show confirm dialog.
  wellLayoutDraft: WellLayoutRow[] | null;
  // Confirmed well->sample mapping; passed to analyze as highest-priority source.
  wellLayout: WellLayout | null;
  clearWellLayout: () => void;
  setInputDir: (path: string) => void;
  setExpectedPath: (path: string) => void;
  setReferencePath: (path: string) => void;
  setOutputPath: (path: string) => void;
  setSampleMapPath: (path: string) => void;
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
  buildWellLayout: () => Promise<void>;
  confirmWellLayout: (rows: WellLayoutRow[]) => void;
  cancelWellLayout: () => void;
  resetInput: () => void;
}

export interface AnalysisSlice {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  summary: AnalyzeSummary | null;
  plateFilter: string;
  searchQuery: string;
  sorting: SortingState;
  showExport: boolean;
  wells: WellEntry[];
  selectedWell: WellEntry | null;
  runHealth: RunHealthData | null;
  setVerdicts: (verdicts: VerdictRecord[]) => void;
  setReplicates: (replicates: ReplicateResult[]) => void;
  setSummary: (summary: AnalyzeSummary | null) => void;
  setPlateFilter: (filter: string) => void;
  setSearchQuery: (query: string) => void;
  setSorting: (updater: Updater<SortingState>) => void;
  openExport: () => void;
  closeExport: () => void;
  setWells: (wells: WellEntry[]) => void;
  setSelectedWell: (well: WellEntry | null) => void;
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
