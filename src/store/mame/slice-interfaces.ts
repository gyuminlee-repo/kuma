import type { SortingState, Updater } from "@tanstack/react-table";
import type {
  AnalyzeSummary,
  ReplicateResult,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";

export interface InputSlice {
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  mode: "amplicon" | "plasmid";
  ingestMode: "barcode" | "amplicon";
  cdsStart: number;
  cdsEnd: number;
  minFileSizeKb: number;
  manyCutoff: number;
  validationErrors: string[];
  isValidating: boolean;
  isAnalyzing: boolean;
  analyzeProgress: number;
  analyzeMessage: string;
  setInputDir: (path: string) => void;
  setExpectedPath: (path: string) => void;
  setReferencePath: (path: string) => void;
  setOutputPath: (path: string) => void;
  setParams: (
    params: Partial<{
      mode: "amplicon" | "plasmid";
      ingestMode: "barcode" | "amplicon";
      cdsStart: number;
      cdsEnd: number;
      minFileSizeKb: number;
      manyCutoff: number;
    }>,
  ) => void;
  setValidationErrors: (errors: string[]) => void;
  setIsAnalyzing: (value: boolean) => void;
  setAnalyzeProgress: (value: number) => void;
  setAnalyzeMessage: (message: string) => void;
  validateInputs: () => Promise<void>;
  runAnalysis: () => Promise<void>;
  cancelAnalysis: () => Promise<void>;
  saveWorkspace: () => Promise<void>;
  loadWorkspace: () => Promise<void>;
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
