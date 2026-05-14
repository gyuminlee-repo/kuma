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

export type InputMode = "consensus" | "sorted_barcode" | "raw_run";

export interface RawRunParams {
  customBarcodesPath: string;
  sequencingSummaryPath: string;
  minQscore: number;
  lengthMin: number;
  lengthMax: number;
  minBarcodeScore: number;
  // R6.5: amplicon length auto-detection
  targetLength: number | null;       // null → auto-detect
  lengthToleranceBp: number;         // ± window around targetLength
  // R6.5: linked trim
  linkedTrim: boolean;               // trim rev primer from 3′ end
  revPrimerUniversal: string;        // 5′→3′ universal rev primer sequence
  // R6.5: header normalization
  normalizeHeaders: boolean;         // write >{well} FASTA headers
}

export interface InputSlice {
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  sampleMapPath: string;
  mode: "amplicon" | "plasmid";
  ingestMode: "barcode" | "amplicon";
  inputMode: InputMode;
  rawRunParams: RawRunParams;
  cdsStart: number;
  cdsEnd: number;
  minFileSizeKb: number;
  minFilteredDepth: number;
  manyCutoff: number;
  validationErrors: string[];
  isValidating: boolean;
  isAnalyzing: boolean;
  isDemuxing: boolean;
  analyzeProgress: number;
  analyzeMessage: string;
  demuxProgress: number;
  demuxMessage: string;
  demuxResult: DemuxAndFilterResult | null;
  distributionStats: DistributionStats | null;
  ampliconLengthEstimate: AmpliconLengthEstimate | null;
  setInputDir: (path: string) => void;
  setExpectedPath: (path: string) => void;
  setReferencePath: (path: string) => void;
  setOutputPath: (path: string) => void;
  setSampleMapPath: (path: string) => void;
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
  validateInputs: () => Promise<void>;
  runDemuxAndFilter: () => Promise<void>;
  runAnalysis: () => Promise<void>;
  cancelAnalysis: () => Promise<void>;
  resetInput: () => void;
}

export interface AnalysisSlice {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  summary: AnalyzeSummary | null;
  plateFilter: "NB01" | "NB02" | "NB03" | "ALL";
  searchQuery: string;
  sorting: SortingState;
  showExport: boolean;
  wells: WellEntry[];
  selectedWell: WellEntry | null;
  runHealth: RunHealthData | null;
  setVerdicts: (verdicts: VerdictRecord[]) => void;
  setReplicates: (replicates: ReplicateResult[]) => void;
  setSummary: (summary: AnalyzeSummary | null) => void;
  setPlateFilter: (filter: "NB01" | "NB02" | "NB03" | "ALL") => void;
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
}

export interface ExportSlice {
  lastExportPath: string | null;
  lastExportAt: string | null;
  isExporting: boolean;
  exportError: string | null;
  exportExcel: (path: string) => Promise<void>;
  resetExport: () => void;
}
