/**
 * Pure interface definitions for each Zustand store slice.
 * This file intentionally imports ONLY from `../../types/models` (no slice
 * implementation files, no `store/types`) so that `store/types.ts` can import
 * from here without creating a circular dependency.
 *
 * Slice implementations import their own interface from this file, and import
 * `AppState` from `../types` — which no longer needs to import from the
 * implementation files.
 */

import type { SortingState, Updater } from "@tanstack/react-table";
import type {
  BenchmarkResult,
  DistanceMode,
  DomainInfo,
  DomainOverlapPolicy,
  DomainStrategy,
  EvolveproStepStats,
  FailedMutation,
  LinkerHandling,
  MutationInputMode,
  ParsedMutation,
  ParseError,
  PlateMapping,
  PolymeraseInfo,
  PolymeraseProfile,
  RescueStats,
  RescuedMutation,
  SdmPrimerResult,
  SequenceInfo,
  UniprotCandidate,
  WorkspaceData,
  WorkspaceV2,
} from "../types/models";

// ---------------------------------------------------------------------------
// SequenceSlice
// ---------------------------------------------------------------------------
export interface SequenceSlice {
  // State
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  selectedGene: string;
  organism: string;

  // Actions
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setOrganism: (organism: string) => void;
}

// ---------------------------------------------------------------------------
// DiversitySlice
// ---------------------------------------------------------------------------
export interface DiversitySlice {
  // State
  pipelineMode: boolean;
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  domainDiversityEnabled: boolean;
  domainStrategy: DomainStrategy;
  domainOverlapPolicy: DomainOverlapPolicy;
  linkerHandling: LinkerHandling;
  domainQuotaMin: number;
  uniprotAccession: string;
  domains: DomainInfo[];
  domainLoading: boolean;
  disabledDomains: string[];
  domainStats: Record<string, { quota: number; selected: number }>;
  paretoDiversityEnabled: boolean;
  entropyWeightEnabled: boolean;
  entropyWeight: number;
  paretoPoolMultiplier: number;
  distanceMode: DistanceMode;
  evolveproRound: number;
  roundSize: number;
  benchmarkTopPercentile: number;
  benchmarkRandomTrials: number;
  benchmarkRandomSeed: number | null;
  benchmarkRunning: boolean;
  showBenchmark: boolean;
  benchmarkResults: Record<string, BenchmarkResult> | null;
  autoRedesignOnLoad: boolean;
  saveCache: boolean;
  structureLoaded: boolean;
  structureLoading: boolean;
  structureAccession: string;
  poolVariants: string[];
  uniprotCandidates: UniprotCandidate[];
  uniprotSearching: boolean;

  // Actions
  setPipelineMode: (enabled: boolean) => void;
  setPositionDiversityEnabled: (enabled: boolean) => void;
  setMaxPerPosition: (n: number) => void;
  setDomainDiversityEnabled: (enabled: boolean) => void;
  setDomainStrategy: (strategy: DomainStrategy) => void;
  setDomainOverlapPolicy: (policy: DomainOverlapPolicy) => void;
  setLinkerHandling: (handling: LinkerHandling) => void;
  setDomainQuotaMin: (value: number) => void;
  fetchDomains: (accession: string, clearCandidates?: boolean) => Promise<void>;
  setDomains: (domains: DomainInfo[]) => void;
  toggleDomain: (domainKey: string) => void;
  setParetoDiversityEnabled: (enabled: boolean) => void;
  setEntropyWeightEnabled: (enabled: boolean) => void;
  setEntropyWeight: (weight: number) => void;
  setParetoPoolMultiplier: (value: number) => void;
  setDistanceMode: (mode: DistanceMode) => void;
  setEvolveproRound: (n: number) => void;
  setRoundSize: (n: number) => void;
  setBenchmarkTopPercentile: (value: number) => void;
  setBenchmarkRandomTrials: (value: number) => void;
  setBenchmarkRandomSeed: (seed: number | null) => void;
  runBenchmark: () => Promise<void>;
  setShowBenchmark: (show: boolean) => void;
  setAutoRedesignOnLoad: (enabled: boolean) => void;
  setSaveCache: (enabled: boolean) => void;
  searchUniprot: (geneName: string, organism: string, translation: string, knownAccession: string) => Promise<void>;
  fetchStructure: (accession: string) => Promise<void>;
  cancelDiversityReload: () => void;
}

// ---------------------------------------------------------------------------
// InputSlice
// ---------------------------------------------------------------------------
export interface InputSlice {
  // State
  mutationInputMode: MutationInputMode;
  mutationText: string;
  parsedMutations: ParsedMutation[];
  parseErrors: ParseError[];
  evolveproCsvPath: string;
  evolveproTotalCount: number;
  evolveproFilteredCount: number | null;
  evolveproParetoExchanges: number | null;
  evolveproStepStats: EvolveproStepStats | null;
  yPredMap: Record<string, number>;

  // Actions
  setMutationInputMode: (mode: MutationInputMode) => void;
  setMutationText: (text: string) => void;
  parseMutations: () => Promise<void>;
  loadEvolveproCsv: (filepath: string, topNOverride?: number) => Promise<void>;
  loadSampleData: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// DesignSlice
// ---------------------------------------------------------------------------
export interface DesignSlice {
  // State
  isDesigning: boolean;
  backendDesignStateSynced: boolean;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  polymerases: PolymeraseInfo[];
  selectedPolymerase: string;
  codonStrategy: "closest" | "optimal";
  maxPrimers: number;
  tmFwdTarget: number;
  tmRevTarget: number;
  tmOverlapTarget: number;
  gcMin: number;
  gcMax: number;
  primerLenEnabled: boolean;
  fwdLenMin: number;
  fwdLenMax: number;
  revLenMin: number;
  revLenMax: number;
  fillOnFailure: boolean;
  manuallySwapped: Record<string, "fwd" | "rev" | "both">;
  customCandidates: Record<string, SdmPrimerResult[]>;
  alternativesCache: Record<string, SdmPrimerResult[]>;
  rescuedMutations: string[];
  rescueStats: RescueStats;
  rescuedMutationDetails: RescuedMutation[];
  showReport: boolean;

  // Actions
  designPrimers: () => Promise<void>;
  setShowReport: (show: boolean) => void;
  cancelDesign: () => Promise<void>;
  getAlternatives: (mutation: string) => Promise<SdmPrimerResult[]>;
  swapPrimer: (mutation: string, candidateIdx: number, swapType?: "both" | "fwd" | "rev") => Promise<void>;
  applyCustomPrimer: (mutation: string, result: SdmPrimerResult) => void;
  addCustomCandidate: (mutation: string, result: SdmPrimerResult) => void;
  removeCustomCandidate: (mutation: string, index: number) => void;
  evaluateCustomPrimer: (mutation: string, fwdSeq: string, revSeq: string, overlapLen?: number) => Promise<SdmPrimerResult>;
  retryFailedMutation: (mutation: string, params: Record<string, number | string>) => Promise<SdmPrimerResult[]>;
  addDesignResult: (mutation: string, result: SdmPrimerResult) => void;
  removeDesignResult: (mutation: string, reason: string) => void;
  setCodonStrategy: (strategy: "closest" | "optimal") => void;
  loadPolymerases: () => Promise<void>;
  setSelectedPolymerase: (name: string) => Promise<void>;
  saveCustomPolymerase: (profile: PolymeraseProfile) => Promise<void>;
  setMaxPrimers: (n: number) => void;
  setTmTargets: (fwd: number, rev: number, ov: number) => void;
  setGcRange: (min: number, max: number) => void;
  setPrimerLenEnabled: (enabled: boolean) => void;
  setPrimerLenRange: (fwdMin: number, fwdMax: number, revMin: number, revMax: number) => void;
  setFillOnFailure: (enabled: boolean) => void;
}

// ---------------------------------------------------------------------------
// ExportSlice
// ---------------------------------------------------------------------------
export interface ExportSlice {
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  progress: number;
  statusMessage: string;
  tableSorting: SortingState;
  getPlateMap: () => Promise<void>;
  exportExcel: (filepath: string, projectId?: string) => Promise<void>;
  setTableSorting: (updater: Updater<SortingState>) => void;
  setStatus: (msg: string) => void;
  getWorkspaceSnapshot: () => WorkspaceV2;
  restoreWorkspace: (ws: WorkspaceData) => Promise<void>;
  resetAll: () => void;
}
