/** TypeScript interfaces for KURO JSON-RPC communication. */

export interface PolymeraseInfo {
  name: string;
  manufacturer: string;
  fidelity: string;
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
}

export interface SearchUniprotResult {
  candidates: UniprotCandidate[];
  auto_selected: string | null;
  error_detail?: string;
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
}

export interface DomainInfo {
  name: string;
  id: string;         // InterPro/Pfam ID (예: "PF01397")
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

export interface EvolveproLoadResult {
  variants: string[];
  y_preds: number[];
  total_count: number;
  selected_count: number;
  filtered_count?: number;
  domain_stats?: Record<string, DomainStat>;
  pareto_replaced?: number;
}

export interface FailedMutation {
  mutation: string;
  rank: number;
  reason: string;
}

export interface DesignResult {
  results: SdmPrimerResult[];
  success_count: number;
  total_count: number;
  failed_mutations: FailedMutation[];
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

export type ExperimentStatus = "pending" | "success" | "failure";
export type FailureReason = "no_colony" | "wrong_size" | "multiple_bands" | "sequencing_mismatch" | "other";

export interface ExperimentResult {
  status: ExperimentStatus;
  failureReason?: FailureReason;
  note?: string;
  timestamp?: string;
}

export interface WorkspaceV1 {
  version: 1;
  fastaPath: string;
  mutationInputMode: "text" | "evolvepro" | "multi-evolve";
  mutationText: string;
  evolveproCsvPath: string;
  selectedGene: string;
  codonStrategy: "closest" | "optimal";
  maxPrimers: number;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  tableSorting: unknown[];
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
  // Domain diversity (optional, 하위호환)
  uniprotAccession?: string;
  domains?: DomainInfo[];
  domainDiversityEnabled?: boolean;
  domainStrategy?: "proportional" | "equal";
  paretoDiversityEnabled?: boolean;
  disabledDomains?: string[];
  entropyWeightEnabled?: boolean;
  organism?: string;
  pipelineMode?: boolean;
  positionDiversityEnabled?: boolean;
  maxPerPosition?: number;
  experimentResults?: Record<string, ExperimentResult>;
}

export interface EsmEmbeddingResult {
  success: boolean;
  accession?: string;
  length?: number;
  dimension?: number;
  error?: string;
}

export interface BenchmarkResult {
  n_selected: number;
  hit_rate: number;
  mean_fitness: number;
  unique_positions: number;
  position_coverage: number;
  hits: number;
  threshold: number;
  n_trials?: number;
}

export interface RunBenchmarkResult {
  results: Record<string, BenchmarkResult>;
}

// JSON-RPC types

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  id: number | null;
  result?: T;
  error?: { code: number; message: string };
}

export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params: Record<string, unknown>;
}

export interface ProgressNotification {
  value: number;
  message: string;
}
