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
import type { Round } from "../types/round";
import type {
  BenchmarkResult,
  ComputeDispersionResult,
  DistanceMode,
  DomainInfo,
  DomainOverlapPolicy,
  DomainStrategy,
  EvolveproPreview,
  EvolveproStepStats,
  FailedMutation,
  FetchActiveSiteResult,
  FetchPdbTextResult,
  LinkerHandling,
  MutationInputMode,
  OverlapMode,
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
  WorkspaceV3,
} from "../types/models";
import type { RankedCandidateItem, SettingsBundle } from "../types/models.generated";

export type EvolveproMode = "topN" | "pipeline" | "others";

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
  structuralDiversityEnabled: boolean;
  structuralKappa: number;


  // Actions
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
  setStructuralDiversityEnabled: (enabled: boolean) => void;
  setStructuralKappa: (v: number) => void;
  /** Fetch PDB text for a given UniProt accession. Results are cached per accession. */
  fetchPdbText: (accession: string) => Promise<FetchPdbTextResult | null>;
  /** Fetch active-site and binding-site residues for a given UniProt accession. */
  fetchActiveSite: (accession: string) => Promise<FetchActiveSiteResult | null>;
  /** Run 3D structural dispersion analysis for a given set of positions. */
  computeDispersion: (args: {
    accession: string;
    refSeq: string;
    positions: number[];
    nTrials?: number;
    seed?: number | null;
  }) => Promise<ComputeDispersionResult | null>;
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
  /** EVOLVEpro selection mode: "topN" | "pipeline" | "others" */
  evolveproMode: EvolveproMode;
  evolveproVariantColumn: string | null;
  evolveproScoreColumn: string | null;
  evolveproScoreOrder: "desc" | "asc";
  evolveproSheetName: string | null;
  evolveproPreview: EvolveproPreview | null;
  othersSourcePath: string;
  othersVariantColumn: string | null;
  othersScoreColumn: string | null;
  othersScoreOrder: "desc" | "asc";
  othersSheetName: string | null;
  othersPreview: EvolveproPreview | null;
  othersUsedVariantColumn: string | null;
  othersUsedScoreColumn: string | null;
  /** Ranked candidate buffer from load_evolvepro_csv response (y_pred desc). */
  evolveproRankedCandidates: RankedCandidateItem[];
  /** Explicit user selection: variant strings that are currently included. */
  evolveproSelectedVariants: string[];
  /** Number of extra (unselected) candidates to expose in the picker UI. */
  evolveproExtraExposed: number;

  // Actions
  setMutationInputMode: (mode: MutationInputMode) => void;
  setMutationText: (text: string) => void;
  parseMutations: () => Promise<void>;
  loadEvolveproCsv: (filepath: string, topNOverride?: number, preserveSelection?: boolean) => Promise<void>;
  loadSampleData: () => Promise<void>;
  setEvolveproMode: (mode: EvolveproMode) => void;
  setEvolveproVariantColumn: (col: string | null) => void;
  setEvolveproScoreColumn: (col: string | null) => void;
  setEvolveproScoreOrder: (order: "desc" | "asc") => void;
  setEvolveproSheetName: (name: string | null) => void;
  setEvolveproPreview: (preview: EvolveproPreview | null) => void;
  setOthersSourcePath: (path: string) => void;
  setOthersVariantColumn: (col: string | null) => void;
  setOthersScoreColumn: (col: string | null) => void;
  setOthersScoreOrder: (order: "desc" | "asc") => void;
  setOthersSheetName: (name: string | null) => void;
  setOthersPreview: (preview: EvolveproPreview | null) => void;
  /**
   * Round handoff hydration.
   * prevRound.merged_table를 필터링하여 EVOLVEpro 형식으로 inputSlice를 hydrate.
   * 0 rows 통과 시 ok=false, 상태 변경 없음.
   * roundSlice.handoffNextRound에서만 호출할 것 (spec §4.5).
   */
  loadRoundActivity: (prevRound: Round) => { ok: boolean; warnings: string[] };
  /** Toggle individual candidate inclusion in EVOLVEpro picker. */
  setEvolveproVariantSelected: (variant: string, selected: boolean) => void;
  /** Set number of extra (unselected) candidates shown in picker. */
  setEvolveproExtraExposed: (count: number) => void;
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
  tmTolerance: number;
  overlapMode: OverlapMode;
  /** §12 Optional RNG seed. null = non-deterministic (backend default). */
  randomSeed: number | null;
  manuallySwapped: Record<string, "fwd" | "rev" | "both">;
  customCandidates: Record<string, SdmPrimerResult[]>;
  alternativesCache: Record<string, SdmPrimerResult[]>;
  rescuedMutations: string[];
  rescueStats: RescueStats;
  rescuedMutationDetails: RescuedMutation[];
  /** @deprecated Phase C (v0.9.2): popup auto-mount removed. Report now renders
   * inline via DesignReportInspector. Slice retained for legacy Dialog wrapper
   * (DesignReport.tsx) in case manual entry is reintroduced. Do not persist. */
  showReport: boolean;

  // Actions
  designPrimers: () => Promise<void>;
  /** @deprecated See showReport — legacy Dialog wrapper only. */
  setShowReport: (show: boolean) => void;
  cancelDesign: () => Promise<void>;
  getAlternatives: (mutation: string) => Promise<SdmPrimerResult[]>;
  swapPrimer: (mutation: string, candidateIdx: number, swapType?: "both" | "fwd" | "rev") => Promise<void>;
  applyCustomPrimer: (mutation: string, result: SdmPrimerResult) => void;
  addCustomCandidate: (mutation: string, result: SdmPrimerResult) => void;
  removeCustomCandidate: (mutation: string, index: number) => void;
  evaluateCustomPrimer: (mutation: string, fwdSeq: string, revSeq: string, overlapLen?: number) => Promise<SdmPrimerResult>;
  retryFailedMutation: (mutation: string, params: Record<string, number | string>) => Promise<SdmPrimerResult[]>;
  /**
   * After a design completes with failures, retry each failed mutation once
   * using parameters derived from the run already-successful primers
   * (median Tm, observed GC/length range, tol_max ±5°C). No-op when no
   * successful primers exist or when fillOnFailure already substituted them.
   */
  autoRetryFailedWithSuggestion: () => Promise<void>;
  cascadeFailedRetry: (mode: "topn-fill" | "pipeline-fill") => Promise<void>;
  addDesignResult: (mutation: string, result: SdmPrimerResult) => void;
  /**
   * Commit a cascade-rescue candidate to the backend _state.results so
   * Excel export (expected_mutations sheet) includes it.
   * candidate_idx 0 = best candidate (always used in cascade paths).
   */
  commitDesignResult: (mutation: string, candidateIdx?: number) => Promise<void>;
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
  setTmTolerance: (value: number) => void;
  setOverlapMode: (mode: OverlapMode) => void;
  setRandomSeed: (seed: number | null) => void;
}

// ---------------------------------------------------------------------------
// NetworkConsentSlice
// ---------------------------------------------------------------------------
export interface NetworkConsentSlice {
  // State
  /** 외부 서비스 호출 동의 여부 */
  networkConsentGranted: boolean;
  /** 오프라인 모드 (true = 외부 호출 차단) */
  offlineMode: boolean;
  /** 동의 모달 표시 여부 */
  networkConsentPending: boolean;

  // Actions
  /** 앱 시작 시 저장된 설정 로드 */
  loadNetworkConsentSettings: () => void;
  /** 동의 처리 (모달 확인) */
  grantNetworkConsent: () => void;
  /** 동의 거부 (모달 취소) */
  denyNetworkConsent: () => void;
  /** 오프라인 모드 토글 */
  setOfflineMode: (enabled: boolean) => void;
  /**
   * 외부 네트워크 호출 진입 전 호출.
   * - offlineMode ON: false 즉시 반환
   * - 동의 완료: true 즉시 반환
   * - 미동의: 동의 모달 표시 후 Promise resolve
   */
  requireNetworkConsent: () => Promise<boolean>;
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
  /** true while an export RPC is in flight (Excel, mapping, benchmark) */
  isExporting: boolean;
  echoTransferVol: number;
  janusTransferVol: number;
  getPlateMap: () => Promise<void>;
  exportExcel: (filepath: string, projectId?: string) => Promise<void>;
  setEchoTransferVol: (value: number) => void;
  setJanusTransferVol: (value: number) => void;
  setTableSorting: (updater: Updater<SortingState>) => void;
  setStatus: (msg: string) => void;
  getWorkspaceSnapshot: () => WorkspaceV3;
  restoreWorkspace: (ws: WorkspaceData) => Promise<void>;
  resetAll: () => void;
}

// ---------------------------------------------------------------------------
// JobQueueSlice — §13 Background Job Queue
// ---------------------------------------------------------------------------
export type { JobKind, JobStatus, Job, JobQueueSlice } from "./slices/jobQueueSlice";

// ---------------------------------------------------------------------------
// LogSlice — §2 Observability: rolling log buffer
// ---------------------------------------------------------------------------
export type { LogSlice } from "./slices/logSlice";

// ---------------------------------------------------------------------------
// NavigationSlice — Phase C subnav + sub-step navigation
// ---------------------------------------------------------------------------
export type {
  MajorStepId,
  SubStepId,
  StepStatus,
  NavigationSlice,
} from "./slices/navigationSlice";
export { MAJOR_ORDER, SUBSTEP_ORDER } from "./slices/navigationSlice";

// ---------------------------------------------------------------------------
// MemorySlice — §19 Performance Guardrails: RSS memory monitor
// ---------------------------------------------------------------------------
export interface MemoryWarning {
  ratio: number;
  rss_mb: number;
  level: "warn" | "block";
}

export interface MemorySlice {
  /** null = no warning active */
  memoryWarning: MemoryWarning | null;
  setMemoryWarning: (w: MemoryWarning | null) => void;
}

// ---------------------------------------------------------------------------
// SettingsSlice
// ---------------------------------------------------------------------------
export interface SettingsSlice {
  // State
  settings: SettingsBundle | null;
  isDirty: boolean;
  isLoading: boolean;
  lastSavedAt: number | null;

  // Actions
  /** IPC settings_load 호출 → state 갱신. App mount 시 자동 호출. */
  loadSettings: () => Promise<void>;
  /** 부분 업데이트 즉시 적용 + debounce 500ms 자동 저장. */
  updateSettings: (partial: Partial<SettingsBundle>) => void;
  /** IPC settings_save 호출 → lastSavedAt 갱신. */
  saveSettings: () => Promise<void>;
  resetDirty: () => void;
}
