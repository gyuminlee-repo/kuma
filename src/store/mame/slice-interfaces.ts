import type { SortingState, Updater } from "@tanstack/react-table";
import type {
  AnalyzeSummary,
  DistributionStats,
  DemuxAndFilterResult,
  ReplicateResult,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";
import type { KumaProject } from "@/state/projectContext";

export type InputMode = "consensus" | "sorted_barcode" | "raw_run";

export interface RawRunParams {
  customBarcodesPath: string;
  sequencingSummaryPath: string;
  minQscore: number;
  lengthMin: number;
  lengthMax: number;
  minBarcodeScore: number;
}

export interface InputSlice {
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  mode: "amplicon" | "plasmid";
  ingestMode: "barcode" | "amplicon";
  inputMode: InputMode;
  rawRunParams: RawRunParams;
  cdsStart: number;
  cdsEnd: number;
  minFileSizeKb: number;
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
  setInputDir: (path: string) => void;
  setExpectedPath: (path: string) => void;
  setReferencePath: (path: string) => void;
  setOutputPath: (path: string) => void;
  setParams: (
    params: Partial<{
      mode: "amplicon" | "plasmid";
      ingestMode: "barcode" | "amplicon";
      inputMode: InputMode;
      rawRunParams: Partial<RawRunParams>;
      cdsStart: number;
      cdsEnd: number;
      minFileSizeKb: number;
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
  validateInputs: () => Promise<void>;
  runDemuxAndFilter: () => Promise<void>;
  runAnalysis: () => Promise<void>;
  cancelAnalysis: () => Promise<void>;
  saveWorkspace: (project: KumaProject) => Promise<void>;
  loadWorkspace: (project: KumaProject) => Promise<void>;
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
  clearResults: () => void;
  loadSampleData: () => void;
}

export interface ExportSlice {
  lastExportPath: string | null;
  lastExportAt: string | null;
  isExporting: boolean;
  exportError: string | null;
  exportExcel: (path: string) => Promise<void>;
}
