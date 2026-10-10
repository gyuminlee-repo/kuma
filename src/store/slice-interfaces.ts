import type { EchoQuadrant } from "@/types/models";
import type { RoundPicks } from "@/lib/plateRounds";
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
import type { ExpectedCodonTable } from "../lib/codonTableRestore";
import type { Round } from "../types/round";
import type {
  BenchmarkResult,
  ComputeCodonTableParams,
  ComputeCodonTableResult,
  ComputeDispersionResult,
  DesignRunRecord,
  DistanceMode,
  DomainInfo,
  DomainOverlapPolicy,
  DomainStrategy,
  EvolveproPreview,
  EvolveproStepStats,
  StrictSpatialResult,
  StrictSpatialBudgetMode,
  PredictionBundleInventory,
  FailedMutation,
  FetchActiveSiteResult,
  FetchPdbTextResult,
  PredictStructureEsmfoldResult,
  LinkerHandling,
  MutationInputMode,
  CodonTableFailure,
  ExportCodonTableParams,
  ImportCodonTableParams,
  ImportCodonTableResult,
  OrganismSummary,
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

export type EvolveproMode = "topN" | "pipeline";

// ---------------------------------------------------------------------------
// SequenceSlice
// ---------------------------------------------------------------------------
export interface SequenceSlice {
  // State
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  selectedGene: string;
  organism: string;
  // Codon tables the sidecar found on this machine. Empty until the sidecar
  // reports ready, and empty again if the list call fails, so every consumer
  // has to tolerate a selection that is not in it.
  organisms: OrganismSummary[];
  // Files in the user codon-table folder that did not load. Shown in Settings
  // rather than swallowed: a table that is silently ignored is worse than one
  // that is rejected out loud, because the user goes on believing it is in use.
  codonTableFailures: CodonTableFailure[];
  // The folder path the sidecar resolved, or null before the first listing.
  // Never reconstructed in the frontend; see ListOrganismsResult.
  codonTableDir: string | null;
  // What a restored project says its codon table was, or null when nothing has
  // been restored. Held as an expectation rather than resolved once at restore
  // time because hydration can run before the first listing lands, where every
  // key would read as "not installed here" (lib/codonTableRestore.ts).
  restoredCodonTable: ExpectedCodonTable | null;

  // Actions
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setOrganism: (organism: string) => void;
  loadOrganisms: () => Promise<void>;
  setRestoredCodonTable: (expected: ExpectedCodonTable | null) => void;
  /**
   * Write the project's copy of the codon table into the user folder and
   * re-list. Resolves to the failure reason, or null on success.
   *
   * Only ever called from an explicit user action: the project's copy is the
   * authoritative one, and overwriting a local table of the same key still
   * needs saying so out loud (design note section 8.3, last row).
   */
  installRestoredCodonTable: () => Promise<string | null>;
  /**
   * Validate a table file without installing it, for the import preview.
   *
   * The same RPC the install uses with `dry_run` set, so the findings the
   * dialog shows before importing are the findings the import produces rather
   * than a second implementation of the same rules. Rejections come back as a
   * result with `ok: false`, not as a throw: they are the expected answer for
   * a file the user picked, and the dialog renders every rule that fired.
   */
  previewCodonTable: (params: ImportCodonTableParams) => Promise<ImportCodonTableResult>;
  /**
   * Install a codon table and select it.
   *
   * Follows saveCustomPolymerase exactly: send, re-list, select. The re-list
   * is what makes the new key selectable, and selecting it is what the user
   * came to do -- an import that left the dropdown on the previous organism
   * would look like it had failed.
   */
  importCodonTable: (params: ImportCodonTableParams) => Promise<ImportCodonTableResult>;
  /**
   * Count a genome into a codon table without installing it, for the preview.
   *
   * `dry_run` again, and again the same RPC the install uses. The scan runs
   * either way -- there is no cheaper way to learn how many coding sequences a
   * file holds than to read them -- so what the preview saves is the write,
   * not the work.
   */
  previewComputedCodonTable: (
    params: ComputeCodonTableParams,
  ) => Promise<ComputeCodonTableResult>;
  /**
   * Count a genome into a codon table, install it and select it.
   *
   * Same send -> relist -> select as importCodonTable, because it is the same
   * outcome: a key in the dropdown the user came here to design with.
   */
  computeCodonTable: (
    params: ComputeCodonTableParams,
  ) => Promise<ComputeCodonTableResult>;
  /** Write an installed table out as a file. Resolves to the path written. */
  exportCodonTable: (params: ExportCodonTableParams) => Promise<string>;
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
  // Whether the last EVOLVEpro load actually used 3D distance, and if not, why.
  // "off": no 3D consumer enabled, so the distinction does not apply.
  // "active": a structure was used for structural/pareto selection.
  // "no_structure": a 3D consumer is on but no structure was loaded.
  // "frame_mismatch": a structure was loaded but does not match the CDS frame.
  // Persisted from the load result so the fallback is visible, not just a
  // transient status line.
  structure3dState: "off" | "active" | "no_structure" | "frame_mismatch";
  poolVariants: string[];
  uniprotCandidates: UniprotCandidate[];
  uniprotSearching: boolean;
  structuralDiversityEnabled: boolean;
  structuralKappa: number;
  /** Session-only opt-in; restored workspaces require an explicit new selection. */
  strictSpatialEnabled: boolean;
  strictSpatialBudgetMode: StrictSpatialBudgetMode;
  strictSpatialSiteCap: number | null;
  strictSpatialSelection: { result: StrictSpatialResult; contextKey: string } | null;
  strictSpatialError: string | null;
  strictStructureSource: "accession" | "prediction_bundle";
  predictionBundlePath: string;
  predictionBundleInventory: PredictionBundleInventory | null;
  predictionBundleModelId: string | null;
  predictionBundleChainId: string | null;
  predictionBundleLoading: boolean;
  predictionBundleError: string | null;
  predictionBundleRevision: number;
  refDomains: DomainInfo[];
  refDomainsLoading: boolean;
  refDomainHash: string;



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
  loadStructureFile: (filepath: string) => Promise<void>;
  cancelDiversityReload: () => void;
  setStructuralDiversityEnabled: (enabled: boolean) => void;
  setStructuralKappa: (v: number) => void;
  setStrictSpatialEnabled: (enabled: boolean) => void;
  setStrictSpatialBudgetMode: (mode: StrictSpatialBudgetMode) => void;
  setStrictSpatialSiteCap: (cap: number | null) => void;
  setStrictStructureSource: (source: "accession" | "prediction_bundle") => void;
  inspectPredictionBundle: (filepath: string) => Promise<void>;
  setPredictionBundleModelId: (modelId: string | null) => void;
  setPredictionBundleChainId: (chainId: string | null) => void;
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
    pdbText?: string | null;
    coordinateFrame?: "accession" | "reference";
  }) => Promise<ComputeDispersionResult | null>;
  /** Predict a reference-frame structure from sequence alone via ESMFold (<=400 aa). */
  predictStructureEsmfold: (sequence: string) => Promise<PredictStructureEsmfoldResult | null>;
  /** Annotate reference-frame domains by submitting the selected gene translation to InterProScan. */
  annotateReferenceDomains: () => Promise<void>;
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
  /** EVOLVEpro selection mode: "topN" | "pipeline" */
  evolveproMode: EvolveproMode;
  evolveproVariantColumn: string | null;
  evolveproScoreColumn: string | null;
  evolveproScoreOrder: "desc" | "asc";
  evolveproSheetName: string | null;
  evolveproPreview: EvolveproPreview | null;
  /** Column name the backend actually used (auto-detected or explicit override), from the last load response. */
  evolveproUsedVariantColumn: string | null;
  evolveproUsedScoreColumn: string | null;
  /** Ranked candidate buffer from load_evolvepro_csv response (y_pred desc). */
  evolveproRankedCandidates: RankedCandidateItem[];
  /** Explicit user selection: variant strings that are currently included. */
  evolveproSelectedVariants: string[];
  /**
   * True once the selection was set by hand (picker toggles, round activity)
   * rather than seeded from the design count. A seeded selection follows
   * `maxPrimers` (`resizeEvolveproSelection`); a hand-set one is left alone.
   * Saved with the selection (KURO snapshot schema 8+). A restore that keeps
   * the saved selection keeps this flag with it; a restore that reloads the
   * CSV reseeds the selection and resets the flag to false.
   */
  evolveproSelectionManual: boolean;
  /** Number of extra (unselected) candidates to expose in the picker UI. */
  evolveproExtraExposed: number;
  /**
   * True once the operator chose the EVOLVEpro table (Browse or a drop onto
   * the window). While true the project manifest never auto-fills the field.
   * Kept in the store and the KURO snapshot (schema 8+) so a tab switch or a
   * restart does not forget the choice. Cleared by resetAll.
   */
  evolveproCsvUserPicked: boolean;

  // Actions
  setMutationInputMode: (mode: MutationInputMode) => void;
  setMutationText: (text: string) => void;
  parseMutations: () => Promise<void>;
  loadEvolveproCsv: (filepath: string, topNOverride?: number, preserveDesignResults?: boolean, preserveSelection?: boolean) => Promise<void>;
  loadSampleData: () => Promise<void>;
  setEvolveproMode: (mode: EvolveproMode) => void;
  setEvolveproVariantColumn: (col: string | null) => void;
  setEvolveproScoreColumn: (col: string | null) => void;
  setEvolveproScoreOrder: (order: "desc" | "asc") => void;
  setEvolveproSheetName: (name: string | null) => void;
  setEvolveproPreview: (preview: EvolveproPreview | null) => void;
  setEvolveproCsvUserPicked: (picked: boolean) => void;
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
  /**
   * Trace of the last design run (success, failure, cancel, sidecar loss).
   * Survives result invalidation so an empty output step can say whether a
   * design ever ran. Session-scoped, never persisted.
   */
  lastDesignRun: DesignRunRecord | null;
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
/**
 * The external services the Settings dialog lets a user switch off one at a
 * time. Each name is the suffix of the `consent_*` field in the settings
 * bundle, so the guard can look a service up without a second mapping table.
 */
export type NetworkService = "uniprot" | "blast" | "alphafold" | "interpro" | "esmfold";

export interface NetworkConsentSlice {
  // State
  /** 외부 서비스 호출 동의 여부 */
  networkConsentGranted: boolean;
  /**
   * 동의 시 모달이 나열한 서비스. null 은 목록을 기록하기 전의 동의로,
   * 당시 네 서비스(uniprot, blast, alphafold, interpro)만 덮는다.
   */
  networkConsentServices: string[] | null;
  /** 오프라인 모드 (true = 외부 호출 차단) */
  offlineMode: boolean;
  /** 동의 모달 표시 여부 */
  networkConsentPending: boolean;
  /** EBI 연락 이메일 입력 창 표시 여부 */
  contactEmailPending: boolean;

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
   * - `service` 가 Settings 에서 꺼져 있으면: false 즉시 반환 (모달 없음)
   * - 동의 완료이고 그 동의가 `service` 를 나열했으면: true 즉시 반환
   *   (나열하지 않은 새 수신처면 모달을 다시 띄운다)
   * - 미동의: 동의 모달 표시 후 Promise resolve
   *
   * `service` 를 생략하면 서비스별 스위치는 건너뛰고 전역 동의만 본다.
   * 호출부가 어느 서비스를 부르는지 알면 반드시 넘긴다: 넘기지 않으면 그
   * 서비스의 Settings 스위치가 아무 일도 하지 않는다.
   */
  requireNetworkConsent: (service?: NetworkService) => Promise<boolean>;
  /**
   * Settings 의 서비스별 스위치 상태. 꺼져 있으면 false.
   * 번들에 키가 없으면 켜진 것으로 본다 (Pydantic 기본값과 같다).
   */
  isNetworkServiceEnabled: (service: NetworkService) => boolean;
  /**
   * 사이드카가 `contact_email_required` 를 돌려줬을 때 호출한다. 이메일
   * 입력 창을 띄우고, 저장이 끝나면 true, 취소하면 false 로 resolve 한다.
   * 동시에 부른 호출부는 창 하나를 함께 기다린다. 네트워크 동의 뒤에만
   * 부른다: 동의 없이 사이드카까지 간 요청은 없기 때문이다.
   */
  requireContactEmail: () => Promise<boolean>;
  /**
   * 입력 창의 저장. 형식이 틀리면 false 를 돌려주고 창을 닫지 않는다.
   * 맞으면 preferences.json 에 저장을 마친 뒤 대기 중인 호출부를 재개한다.
   */
  submitContactEmail: (email: string) => Promise<boolean>;
  /** 입력 창의 취소. 대기 중인 호출부는 EBI 단계를 건너뛴다. */
  cancelContactEmail: () => void;
}

// ---------------------------------------------------------------------------
// ExportSlice
// ---------------------------------------------------------------------------
/** Macrogen order amount in μmole. */
export type ExportAmount = "0.05" | "0.2";
/** Forward and reverse order plate names per round label. */
export type ExportPlateNames = Record<string, { fwd: string; rvs: string }>;

export interface ExportSlice {
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  progress: number;
  statusMessage: string;
  tableSorting: SortingState;
  /** true while an export RPC is in flight (Excel, mapping, benchmark) */
  isExporting: boolean;
  echoTransferVol: number;
  /**
   * 이 round 가 차지할 384 Echo source plate 의 열 패리티. "A1" 은 홀수 열
   * 1, 3 .. 23, "A2" 는 짝수 열 2, 4 .. 24 다. null 이면 열을 건너뛰지 않는
   * 기존 row-doubled 배치를 쓴다. reverse 는 같은 열에서 forward 바로 아래
   * 행으로 간다.
   */
  echoQuadrant: EchoQuadrant | null;
  /** 이 plate 에서 이미 소진된 절반. 작업자가 직접 입력한다. */
  echoUsedQuadrants: EchoQuadrant[];
  /**
   * 한 플레이트를 넘는 설계를 라운드로 나눠 내보낼 때 라운드마다 작업자가 고른
   * Echo 소스 플레이트 번호(1부터)와 열 패리티. 0 번이 R1 이다. 자동 배정하지
   * 않으므로 기본값은 없다(빈 목록, 없는 칸은 미선택). 라운드를 낼 때 같은
   * 플레이트의 앞 라운드 패리티가 used_quadrants 로 넘어가고, 같은 (플레이트,
   * 패리티)를 두 라운드가 쓰지 못한다. 저장 파일에서 읽을 때는
   * `normalizeRoundPicks` 한 곳만 지난다.
   */
  echoRoundPicks: RoundPicks;
  /**
   * 방금 연 프로젝트가 v0.16.61 의 half layout 으로 저장돼 선택을 떨어뜨렸으면 그때
   * 읽은 저장값들. null 이면 떨어뜨린 것이 없다. 저장하지 않는 파생 값이며
   * 불러올 때마다 다시 판정한다(`foldPersistedPlacement`). 작업자가 소진 표시를
   * 고치면 지운다. 조용히 버리면 소스 웰이 말없이 옮겨간다.
   */
  echoLegacyPlacement: string[] | null;
  janusTransferVol: number;
  /**
   * Step 6 export form fields. Kept here, not in the form, so leaving the step
   * or reopening the project (KURO snapshot schema 8+) does not clear them.
   * `exportPlateNames` is keyed by round label ("single" outside rounds,
   * "R1", "R2" ... in rounds). Names for a round the current design no
   * longer has are kept and not shown or sent, so they come back if the
   * round count does.
   */
  exportName: string;
  exportPlateNames: ExportPlateNames;
  exportAmount: ExportAmount;
  exportVectormaps: boolean;
  getPlateMap: () => Promise<void>;
  exportExcel: (filepath: string, projectId?: string) => Promise<void>;
  setEchoTransferVol: (value: number) => void;
  setEchoQuadrant: (value: EchoQuadrant | null) => void;
  setEchoUsedQuadrants: (value: EchoQuadrant[]) => void;
  setEchoRoundPicks: (value: RoundPicks) => void;
  setJanusTransferVol: (value: number) => void;
  setExportName: (value: string) => void;
  setExportPlateName: (key: string, direction: "fwd" | "rvs", value: string) => void;
  setExportAmount: (value: ExportAmount) => void;
  setExportVectormaps: (value: boolean) => void;
  setTableSorting: (updater: Updater<SortingState>) => void;
  setStatus: (msg: string) => void;
  getWorkspaceSnapshot: () => WorkspaceV3;
  restoreWorkspace: (ws: WorkspaceData) => Promise<void>;
  resetAll: (options?: { preserveWorkspaceArtifacts?: boolean }) => void;
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
  /**
   * The address EBI submissions actually carry and its source, as the last
   * settings_load reported it. The environment variable wins over the Settings
   * field and the legacy config file fills in when the field is empty, so the
   * field alone cannot say what is sent. Null before a load or from a sidecar
   * that does not report it.
   */
  contactEmailResolution: {
    email: string | null;
    source: "env" | "preferences" | "legacy_config" | "none";
  } | null;

  // Actions
  /** IPC settings_load 호출 → state 갱신. App mount 시 자동 호출. */
  loadSettings: () => Promise<void>;
  /**
   * The one theme setter. Every entry point (toolbar toggle, both menu bars,
   * the Settings dialog) goes through it, so the choice reaches localStorage
   * and preferences.json together.
   */
  setThemePreference: (next: "light" | "dark" | "system") => void;
  /**
   * The one offline-mode setter for user toggles (Settings and About). Writes
   * the in-memory flag and `network.offline_mode` together. Loading settings
   * uses the raw `setOfflineMode` instead so a load does not trigger a save.
   */
  setOfflinePreference: (value: boolean) => void;
  /** 부분 업데이트 즉시 적용 + debounce 500ms 자동 저장. */
  updateSettings: (partial: Partial<SettingsBundle>) => void;
  /** IPC settings_save 호출 → lastSavedAt 갱신. */
  saveSettings: () => Promise<void>;
  resetDirty: () => void;
}
