import type { SortingState } from "@tanstack/react-table";
import type { SettingsBundle } from "./models.generated";

/** TypeScript interfaces for KURO JSON-RPC communication. */

export type MutationInputMode = "text" | "evolvepro";
export type CodonStrategy = "closest" | "optimal";
export type OverlapMode = "partial" | "full";

export interface PolymeraseInfo {
  name: string;
  manufacturer: string;
  fidelity: string;
}

export interface PolymeraseProfile {
  name: string;
  tm_method: string;
  salt_correction: string;
  opt_tm: number;
  min_tm: number;
  max_tm: number;
  opt_size: number;
  min_size: number;
  max_size: number;
  min_gc: number;
  max_gc: number;
  salt_monovalent: number;
  salt_divalent: number;
  dntp_conc: number;
  dna_conc: number;
  max_tm_diff: number;
  opt_tm_fwd?: number | null;
  opt_tm_rev?: number | null;
  opt_tm_overlap?: number | null;
  min_3prime_dist?: number;
  overlap_len?: number | null;
  fwd_len_min?: number | null;
  fwd_len_max?: number | null;
  rev_len_min?: number | null;
  rev_len_max?: number | null;
  default_overlap_mode?: OverlapMode | null;
}

export interface GeneInfo {
  gene: string;
  product: string;
  cds_start: number;
  cds_end: number;
  aa_length: number;
  organism?: string;
  translation?: string;
  uniprot_accession?: string;
}

export interface UniprotCandidate {
  accession: string;
  name: string;
  organism: string;
  length: number;
  identity: number;
  has_structure?: boolean;
}

export interface SearchUniprotResult {
  candidates: UniprotCandidate[];
  auto_selected: string | null;
  error_detail?: string | null;
}

export interface StructureAvailabilityResult {
  availability: Record<string, boolean>;
}

export interface SequenceInfo {
  header: string;
  seq_length: number;
  genes: GeneInfo[];
}

export interface ParsedMutation {
  raw: string;
  wt_aa: string;
  position: number;
  mt_aa: string;
}

export interface ParseError {
  line: number;
  raw: string;
  reason: string;
}

export interface ParseMutationsResult {
  parsed: ParsedMutation[];
  errors: ParseError[];
}

export interface AlternativesResult {
  mutation?: string;
  count?: number;
  candidates: SdmPrimerResult[];
}

export interface OffTargetHit {
  position: number;
  strand: "sense" | "antisense";
  match_seq: string;
  tm: number;
  match_length: number;
}

export interface SdmPrimerResult {
  mutation: string;
  aa_position: number;
  codon_pos: number;
  forward_seq: string;
  reverse_seq: string;
  fwd_len: number;
  rev_len: number;
  overlap_len: number;
  candidate_count?: number;
  candidate_fwd_count?: number;
  candidate_rev_count?: number;
  tm_no_fwd: number;
  tm_no_rev: number;
  tm_overlap: number;
  tm_condition_met: boolean;
  tolerance_used: number;
  tolerance_fwd?: number;
  tolerance_rev?: number;
  has_offtarget: boolean;
  offtarget_fwd?: OffTargetHit[];
  offtarget_rev?: OffTargetHit[];
  penalty: number;
  gc_fwd: number;
  gc_rev: number;
  wt_codon: string;
  mt_codon: string;
  overlap_seq: string;
  hairpin_tm_fwd?: number;
  hairpin_tm_rev?: number;
  homodimer_tm_fwd?: number;
  homodimer_tm_rev?: number;
  hairpin_dg_fwd?: number;
  hairpin_dg_rev?: number;
  homodimer_dg_fwd?: number;
  homodimer_dg_rev?: number;
  synthesis_score_fwd?: number;
  synthesis_score_rev?: number;
  warnings: string[];
  overlap_mode?: "partial" | "full";
}

export interface DomainInfo {
  name: string;
  id: string;         // InterPro/Pfam ID (e.g. "PF01397")
  start: number;      // 1-based residue position
  end: number;
  db: string;         // "Pfam" | "InterPro" | "manual"
}

export interface FetchDomainsResult {
  accession: string;
  domains: DomainInfo[];
  source: "interpro_api" | "manual" | "error";
  protein_length?: number;
  error_msg?: string;
}

export interface DomainStat {
  quota: number;
  selected: number;
}

export interface EvolveproStepStats {
  position_filter_removed?: number | null;
  domain_selected?: number | null;
  pareto_exchanges?: number | null;
}

export interface EvolveproLoadResult {
  variants: string[];
  y_preds: number[];
  total_count: number;
  selected_count: number;
  filtered_count?: number;
  domain_stats?: Record<string, DomainStat>;
  pareto_replaced?: number;
  pool_variants?: string[];
  step_stats?: EvolveproStepStats;
}

export interface EvolveproPreview {
  sheets: string[];
  headers: string[];
  rows: string[][];
}

export interface FailedMutation {
  mutation: string;
  rank: number;
  reason: string;
}

export interface RescuedMutation {
  original: string;
  rescued_by: string;
  type:
    | "pool_cascade"
    | "auto_relax"
    | "auto_suggestion"
    | "same_position"
    | "diff_position"
    | "auto_suggestion_l1"
    | "auto_suggestion_l2"
    | "auto_suggestion_l3"
    | "auto_suggestion_l4";
  penalty?: number;
  tolerance_used?: number;
  stage?: number;       // 1-6 cascade stage marker
  substitute?: string;  // new mutation string when type is same/diff_position
}

export interface RescueStats {
  pool_cascade: number;
  auto_relax: number;
  positions_attempted: number;
  pool_variants_tried: number;
}

export interface DesignResult {
  results: SdmPrimerResult[];
  success_count: number;
  total_count: number;
  failed_mutations: FailedMutation[];
  rescue_stats?: RescueStats;
  rescued_mutations?: RescuedMutation[];
  cancelled?: boolean;
}

export interface PlateMapping {
  well: string;
  primer_name: string;
  sequence: string;
  primer_type: "forward" | "reverse";
  mutation: string;
  tm?: number;
  tm_overlap?: number;
  wt_codon?: string;
  mt_codon?: string;
}

export interface PlateMapResult {
  mappings: PlateMapping[];
  dedup_info: Record<string, string[]>;
}

export interface ExportResult {
  success: boolean;
  filepath: string;
}

export interface SaveCustomPolymeraseResult {
  success: boolean;
  name: string;
}

export interface ExportOrderResult extends ExportResult {
  format: "idt" | "twist";
  primer_count: number;
}

export interface ExportMappingResult extends ExportResult {
  format: "echo" | "janus";
  primer_count: number;
}

export interface WorkspaceV1 {
  version: 1;
  fastaPath: string;
  mutationInputMode: MutationInputMode;
  mutationText: string;
  evolveproCsvPath: string;
  selectedGene: string;
  codonStrategy: CodonStrategy;
  maxPrimers: number;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  tableSorting: SortingState;
  manuallySwapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  tmFwdTarget: number;
  tmRevTarget: number;
  tmOverlapTarget: number;
  gcMin: number;
  gcMax: number;
  primerLenEnabled?: boolean;
  fwdLenMin?: number;
  fwdLenMax?: number;
  revLenMin?: number;
  revLenMax?: number;
  fillOnFailure?: boolean;
  tmTolerance?: number;
  // Domain diversity (optional, backward-compatible)
  uniprotAccession?: string;
  domains?: DomainInfo[];
  domainDiversityEnabled?: boolean;
  domainStrategy?: "proportional" | "equal";
  paretoDiversityEnabled?: boolean;
  disabledDomains?: string[];
  rescuedMutations?: string[];
  entropyWeightEnabled?: boolean;
  entropyWeight?: number;
  organism?: string;
  pipelineMode?: boolean;
  positionDiversityEnabled?: boolean;
  maxPerPosition?: number;
  evolveproRound?: number;
  roundSize?: number;
  evolveproTotalCount?: number;
  evolveproFilteredCount?: number | null;
  evolveproParetoExchanges?: number | null;
  evolveproStepStats?: EvolveproStepStats | null;
}

export type DistanceMode = "auto" | "1d" | "3d";
export type DomainStrategy = "proportional" | "equal";
export type DomainOverlapPolicy = "first" | "largest";
export type LinkerHandling = "include" | "exclude" | "separate-bin";

export interface WorkspaceInputs {
  fastaPath: string;
  mutationInputMode: MutationInputMode;
  mutationText: string;
  evolveproCsvPath: string;
  selectedGene: string;
}

export interface WorkspaceSettings {
  selectedPolymerase?: string;
  codonStrategy: CodonStrategy;
  maxPrimers: number;
  tmFwdTarget: number;
  tmRevTarget: number;
  tmOverlapTarget: number;
  gcMin: number;
  gcMax: number;
  primerLenEnabled?: boolean;
  fwdLenMin?: number;
  fwdLenMax?: number;
  revLenMin?: number;
  revLenMax?: number;
  fillOnFailure?: boolean;
  tmTolerance?: number;
  uniprotAccession?: string;
  domains?: DomainInfo[];
  domainDiversityEnabled?: boolean;
  domainStrategy?: "proportional" | "equal";
  domainOverlapPolicy?: DomainOverlapPolicy;
  linkerHandling?: LinkerHandling;
  domainQuotaMin?: number;
  paretoDiversityEnabled?: boolean;
  disabledDomains?: string[];
  rescuedMutations?: string[];
  entropyWeightEnabled?: boolean;
  entropyWeight?: number;
  paretoPoolMultiplier?: number;
  distanceMode?: DistanceMode;
  benchmarkTopPercentile?: number;
  benchmarkRandomTrials?: number;
  benchmarkRandomSeed?: number | null;
  autoRedesignOnLoad?: boolean;
  saveCache?: boolean;
  organism?: string;
  pipelineMode?: boolean;
  positionDiversityEnabled?: boolean;
  maxPerPosition?: number;
  evolveproRound?: number;
  roundSize?: number;
  overlapMode?: OverlapMode;
  /** §12 Optional RNG seed for reproducible design runs. */
  randomSeed?: number | null;
}

export interface WorkspaceResults {
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  manuallySwapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutationDetails?: RescuedMutation[];
}

export interface WorkspaceUi {
  tableSorting: SortingState;
}

export interface WorkspaceCache {
  evolveproTotalCount?: number;
  evolveproFilteredCount?: number | null;
  evolveproParetoExchanges?: number | null;
  evolveproStepStats?: EvolveproStepStats | null;
  benchmarkResults?: Record<string, BenchmarkResult> | null;
}

export interface WorkspaceV2 {
  version: 2;
  inputs: WorkspaceInputs;
  settings: WorkspaceSettings;
  results: WorkspaceResults;
  ui: WorkspaceUi;
  cache?: WorkspaceCache;
}

/**
 * WorkspaceV3 — schema_version "0.3" (string discriminator).
 * rounds: Round[] + active_round_id 추가.
 * v0.3 이전 워크스페이스 로드 시 throw.
 */
export interface WorkspaceV3 {
  schema_version: "0.3";
  inputs: WorkspaceInputs;
  settings: WorkspaceSettings;
  results: WorkspaceResults;
  ui: WorkspaceUi;
  cache?: WorkspaceCache;
  rounds: import("./round").Round[];
  active_round_id: string | null;
}

export type WorkspaceData = WorkspaceV1 | WorkspaceV2 | WorkspaceV3;

export interface StructureResult {
  success: boolean;
  accession?: string;
  residues?: number;
  error?: string;
}

export interface BenchmarkResult {
  n_selected: number;
  hit_rate: number;
  mean_fitness: number;
  unique_positions: number;
  position_coverage: number;
  domain_coverage: number;
  structural_spread: number;
  hits: number;
  threshold: number;
  n_trials?: number;
}

export interface RunBenchmarkResult {
  results: Record<string, BenchmarkResult>;
}

export interface JsonRpcError {
  code: number;
  message: string;
}

export interface CancelDesignResult {
  cancelled: boolean;
  active_design?: boolean;
}

export type RpcParams = Record<string, unknown>;

export interface RpcMethodMap {
  list_polymerases: {
    params: Record<string, never>;
    result: PolymeraseInfo[];
  };
  get_polymerase_details: {
    params: { name: string };
    result: PolymeraseProfile;
  };
  save_custom_polymerase: {
    params: PolymeraseProfile;
    result: SaveCustomPolymeraseResult;
  };
  list_organisms: {
    params: Record<string, never>;
    result: Array<{ key: string; name: string; taxid: number }>;
  };
  load_fasta: {
    params: { filepath: string };
    result: SequenceInfo;
  };
  parse_mutations_text: {
    params: { text: string };
    result: ParseMutationsResult;
  };
  design_sdm_primers: {
    params: RpcParams;
    result: DesignResult;
  };
  load_evolvepro_csv: {
    params: RpcParams;
    result: EvolveproLoadResult;
  };
  preview_evolvepro_source: {
    params: RpcParams;
    result: EvolveproPreview;
  };
  get_plate_map: {
    params: Record<string, never>;
    result: PlateMapResult;
  };
  get_alternatives: {
    params: { mutation: string };
    result: AlternativesResult;
  };
  swap_primer: {
    params: { mutation: string; candidate_idx: number; swap_type: "both" | "fwd" | "rev" };
    result: SdmPrimerResult;
  };
  commit_design_result: {
    params: { mutation: string; candidate_idx: number };
    result: SdmPrimerResult;
  };
  export_excel: {
    params: RpcParams;
    result: ExportResult;
  };
  export_order: {
    params: RpcParams & { bom?: boolean };
    result: ExportOrderResult;
  };
  export_mapping: {
    params: RpcParams & { bom?: boolean };
    result: ExportMappingResult;
  };
  export_echo_mapping_dry_run: {
    params: { transfer_vol?: number };
    result: {
      rows: Array<{
        source_plate: string;
        source_well_name: string;
        source_well: string;
        dest_plate: string;
        dest_well_name: string;
        dest_well: string;
        transfer_vol: number;
      }>;
      total: number;
      transfer_vol: number;
    };
  };
  export_janus_mapping_dry_run: {
    params: { transfer_vol?: number };
    result: {
      rows: Array<{
        name: string;
        type: string;
        dsp_rack_label: string;
        no: number;
        asp_rack: number;
        asp_posi: string;
        dsp_rack: number;
        dsp_posi: string;
        volume: number;
      }>;
      total: number;
      transfer_vol: number;
    };
  };
  export_macrogen: {
    params: {
      project_id?: string;
      output_path: string;
      fwd_plate_name?: string;
      rev_plate_name?: string;
      amount?: "0.05" | "0.2";
      purification?: "MOPC";
    };
    result: { ok: true; path: string };
  };
  export_all: {
    params: {
      project_id?: string;
      output_dir: string;
      fwd_plate_name?: string;
      rev_plate_name?: string;
      amount?: "0.05" | "0.2";
      purification?: "MOPC";
      echo_transfer_vol?: number;
      janus_transfer_vol?: number;
      bom?: boolean;
      mappings?: PlateMapping[];
      dedup_info?: Record<string, string[]>;
    };
    result: {
      success: string[];
      failed: { path: string; reason: string }[];
      output_dir: string;
    };
  };
  export_benchmark_csv: {
    params: { filepath: string; results: Record<string, BenchmarkResult>; bom?: boolean };
    result: ExportResult;
  };
  evaluate_primer: {
    params: RpcParams;
    result: SdmPrimerResult;
  };
  retry_failed_mutation: {
    params: RpcParams;
    result: AlternativesResult;
  };
  save_json: {
    params: { filepath: string; data: unknown };
    result: ExportResult;
  };
  save_workspace: {
    params: { filepath: string; data: WorkspaceData };
    result: ExportResult;
  };
  load_workspace: {
    params: { filepath: string };
    result: WorkspaceData;
  };
  fetch_domains: {
    params: { accession: string };
    result: FetchDomainsResult;
  };
  search_uniprot: {
    params: { gene_name: string; organism: string; translation: string; known_accession: string };
    result: SearchUniprotResult;
  };
  check_structures_available: {
    params: { accessions: string[] };
    result: StructureAvailabilityResult;
  };
  fetch_structure: {
    params: { accession: string };
    result: StructureResult;
  };
  run_benchmark: {
    params: RpcParams;
    result: RunBenchmarkResult;
  };
  cancel_design: {
    params: Record<string, never>;
    result: CancelDesignResult;
  };
  // Phase 3: Settings
  settings_load: {
    params: Record<string, never>;
    result: { settings: SettingsBundle };
  };
  settings_save: {
    params: { settings: SettingsBundle };
    result: { ok: boolean; path: string };
  };
}

export type RpcMethod = keyof RpcMethodMap;
export type RpcMethodParams<K extends RpcMethod> = RpcMethodMap[K]["params"];
export type RpcMethodResult<K extends RpcMethod> = RpcMethodMap[K]["result"];

// JSON-RPC types

export interface JsonRpcRequest<K extends RpcMethod = RpcMethod> {
  jsonrpc: "2.0";
  id: number;
  method: K;
  params: RpcMethodParams<K>;
}

export interface JsonRpcSuccessResponse<T = unknown> {
  jsonrpc: "2.0";
  id: number;
  result: T;
  error?: never;
}

export interface JsonRpcErrorResponse {
  jsonrpc: "2.0";
  id: number | null;
  result?: never;
  error: JsonRpcError;
}

export interface ReadyNotification {
  jsonrpc: "2.0";
  method: "ready";
  params: Record<string, never>;
}

export interface ProgressNotification {
  value: number;
  message: string;
}

export interface ProgressNotificationMessage {
  jsonrpc: "2.0";
  method: "progress";
  params: ProgressNotification;
}

export type JsonRpcResponse<T = unknown> = JsonRpcSuccessResponse<T> | JsonRpcErrorResponse;
export type JsonRpcNotification = ReadyNotification | ProgressNotificationMessage;
export type JsonRpcMessage = JsonRpcResponse | JsonRpcNotification;
