import type { ReactNode } from "react";

export type VerdictClass =
  | "PASS"
  | "AMBIGUOUS"
  | "MIXED"
  | "FRAMESHIFT"
  | "MANY"
  | "LOWDEPTH"
  | "NO_CALL"
  | "WRONG_AA";

export type SidecarStatus = "disconnected" | "connecting" | "ready" | "error";

export interface VerdictRecord {
  native_barcode: string;
  custom_barcode: string;
  file_size_kb: number;
  read_count: number | null;
  n_mixed_positions: number;
  max_minor_allele_fraction: number;
  n_low_depth_positions: number;
  consensus_n_fraction: number;
  n_low_quality_bases: number;
  n_input_reads: number | null;
  n_aligned_reads: number | null;
  n_mapq_failed: number;
  n_span_failed: number;
  source_path: string;
  aa_sequence: string;
  observed_nt_changes: string[];
  observed_aa_changes: string[];
  n_no_call_aa: number;
  expected_mutations: string[];
  /**
   * Per-well variant identity assigned by the pipeline (sample_map ground truth
   * in combinatorial-sort runs, else the observation/heuristic grouping result).
   * Authoritative per-well source for the verdict table's mutant-id column.
   * Empty string for legacy payloads persisted before this field existed.
   */
  mutant_id: string;
  verdict: VerdictClass;
  verdict_notes: string;
}

export interface ReplicateResult {
  mutant_id: string;
  selected_plate: string | null;
  selection_reason: string;
  failed: boolean;
  plate_keys: string[];
  // Full verdict dict per native_barcode, serialized by the sidecar
  // (_serialize_replicate). This is the ONLY lossless source for per-plate
  // accent (selected / is_fallback) restoration. The frontend persists +
  // replays the analyze response AS-IS including this field; reconstructing
  // from plate_keys alone silently corrupts well flags.
  plate_verdicts: Record<string, VerdictRecord>;
  is_fallback: boolean;
  fallback_reason: string | null;
}

export interface DistributionFileStats {
  min: number;
  p05: number;
  p25: number;
  median: number;
  p75: number;
  p95: number;
  max: number;
  mean: number;
  std: number;
}

export interface DistributionStats {
  n_files: number;
  file_size_kb: DistributionFileStats;
  suggested_cutoff_kb: number;
  suggested_method: "median_minus_2sigma" | "p05" | "kneedle" | "fixed_50";
  bimodal: boolean;
}

export interface AnalyzeSummary {
  total: number;
  pass_count: number;
  ambiguous_count: number;
  mixed_count?: number;
  fail_count: number;
}

export interface AnalyzeResult {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  output_path: string;
  summary: AnalyzeSummary;
  distribution_stats: DistributionStats;
}

/**
 * Parameters for the `load_analyze_result` RPC (Phase 1 contract). Mirrors the
 * `analyze` response shape so the persisted result can be replayed verbatim to
 * re-inject the sidecar SidecarState on restart. `replicates[].plate_verdicts`
 * MUST be carried through for lossless plate-accent restoration.
 */
export interface LoadAnalyzeResultRequest {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  output_path: string;
  run_meta?: Record<string, unknown> | null;
  summary?: AnalyzeSummary | null;
  distribution_stats?: DistributionStats | null;
}

/** Ack returned by `load_analyze_result`. Counts only; store data comes from
 *  the persisted file, not this response. */
export interface LoadAnalyzeResultResponse {
  restored: true;
  verdict_count: number;
  replicate_count: number;
}

export interface WellEntry {
  well: string;
  barcode: string;
  native_barcode: string;
  verdict: VerdictClass;
  mutant_id: string;
  selected: boolean;
  notes: string;
  is_fallback: boolean;
  fallback_reason: string | null;
}

export interface AnalysisParams {
  input_dir: string;
  reference: string;
  expected: string;
  output: string;
  mode: "amplicon" | "plasmid";
  ingest_mode: "barcode" | "amplicon";
  cds_start: number;
  cds_end: number;
  min_file_size_kb: number;
  min_read_count?: number | null;
  max_consensus_n_fraction?: number | null;
  many_cutoff: number;
  // Raw-run folded analyze: when input_dir is a MinKNOW run folder (contains
  // fastq_pass/), the backend demuxes internally before analyzing. These names
  // are byte-identical to the Pydantic raw-run fields. `reference` above is
  // reused as reference_fasta.
  custom_barcodes_xlsx?: string;
  native_barcodes?: string[] | null;
  coverage_fraction?: number;
  edit_dist_ratio?: number;
  chimera_split?: boolean;
  demux_output_dir?: string;
  mapq_threshold?: number;
  trim_flank_bp?: number;
}

export interface JsonRpcError {
  code: number;
  message: string;
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  id?: number;
  result?: T;
  error?: JsonRpcError;
}

export interface JsonRpcNotification<T = unknown> {
  jsonrpc: "2.0";
  method: string;
  params?: T;
}

export interface ProgressNotification {
  value: number;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

export interface ExportResult {
  output_path: string;
}

export interface JanusExportResult {
  output_path: string;
  format: "csv" | "xlsx";
}

export type JanusExportFormat = "csv" | "xlsx";

export type RunReportFormat = "html" | "pdf";

export interface RunReportResult {
  output_path: string;
  format: RunReportFormat;
  weasyprint_available: boolean;
  fallback_to_html: boolean;
}

export interface PlateDataResult {
  wells: WellEntry[];
}

export interface ScreenTab {
  id: "input" | "verdict" | "plate" | "export";
  label: string;
  content?: ReactNode;
}

// ── A9: Cross-talk detection types ──────────────────────────────────────────

export interface CrossTalkCandidate {
  /** Well label, e.g. "A1", "B6". */
  well: string;
  /** Custom barcode label assigned to the well, e.g. "1_1", "1_2". */
  custom_barcode: string;
  /** Observed read count for this well. */
  read_count: number;
  /** Mean read count of orthogonal neighbors. */
  neighbor_avg: number;
  /** Z-score vs the entire plate-wide distribution. */
  z_score: number;
  severity: "low" | "medium" | "high";
  note: string;
}

// ── A8: Run health panel types ───────────────────────────────────────────────

export interface RunHealthBreakdown {
  pass: number;
  ambiguous: number;
  mixed: number;
  frameshift: number;
  many: number;
  lowdepth: number;
  no_call: number;
  wrong_aa: number;
  fail: number;
  fallback: number;
  total: number;
}

export interface RunHealthThroughputPoint {
  time_h: number;
  reads_per_sec: number;
}

export interface RunHealthData {
  per_plate_summary: Record<string, RunHealthBreakdown>;
  /** Keys: min, p05, p25, median, p75, p95, max, mean, std */
  file_size_distribution: Record<string, number>;
  suggested_cutoff_kb: number;
  bimodal: boolean;
  suggested_method: "median_minus_2sigma" | "p05" | "kneedle" | "fixed_50";
  pore_yield_pct: number | null;
  throughput_timeline: RunHealthThroughputPoint[] | null;
  barcode_distribution: Record<string, number> | null;
  cross_talk_candidates: CrossTalkCandidate[];
}

// ── A1/A3: Demux and quality-filter types (R6.5) ────────────────────────────

export interface DemuxFilterStats {
  n_input: number;
  n_passed: number;
  n_failed_qscore: number;
  n_failed_length: number;
  n_failed_barcode: number;
}

export interface AmpliconLengthDistributionSummary {
  min: number;
  median: number;
  max: number;
  peak_count: number;
  peak_ratio: number;
}

export interface AmpliconLengthEstimate {
  detected_length: number;
  n_sample_reads: number;
  confidence: "high" | "medium" | "low";
  distribution_summary: AmpliconLengthDistributionSummary;
}

// ── A4/A5: Consensus calling statistics per well ────────────────────────────

export interface WellConsensusStats {
  /** Length of the consensus sequence (== reference length). */
  consensus_seq_length: number;
  /** Total reads for this well entering the alignment step. */
  n_input_reads: number;
  /** Reads that passed MAPQ filter and full-span filter. */
  n_aligned: number;
  /** Same as n_aligned (conservative — mappy does not expose pre-filter counts). */
  n_passed_filter: number;
  /** Mean per-position read depth across the reference. */
  mean_depth: number;
}

export interface DemuxAndFilterResult {
  output_dir: string;
  n_input_reads: number;
  n_assigned: number;
  n_unassigned: number;
  per_well_counts: Record<string, number>;
  filter_stats: DemuxFilterStats | null;
  backend: "cutadapt" | "python";
  amplicon_length_estimate: AmpliconLengthEstimate | null;
  length_filter_mode: "target_window" | "fixed_range" | "none";
  /** Number of native barcode subdirs auto-detected from fastq_dir.
   *  Null when nb_dirs was explicitly provided or single-NB fallback occurred. */
  auto_detected_nb_count?: number | null;
  /** Basenames (e.g. "barcode01") of auto-detected NB subdirs. Null in the
   *  same cases as auto_detected_nb_count. */
  auto_detected_nb_names?: string[] | null;
  /** Per-well consensus calling statistics.
   *  Null when reference_fasta was not provided (legacy demux-only mode). */
  consensus_stats?: Record<string, WellConsensusStats> | null;
  /** True when A4/A5 alignment+consensus pipeline was executed. */
  consensus_pipeline?: boolean;
}

export interface DemuxAndFilterParams {
  fastq_dir: string;
  custom_barcodes?: Record<string, string>;
  custom_barcodes_path?: string;
  output_dir: string;
  /** Path to reference FASTA for alignment + consensus calling (A4/A5).
   *  When provided, output per-well FASTA files are single-record consensus
   *  sequences compatible with analyze(). */
  reference_fasta?: string;
  error_tolerance?: number;
  use_cutadapt?: boolean;
  sequencing_summary?: string;
  min_qscore?: number;
  length_min?: number;
  length_max?: number;
  target_length?: number | null;
  length_tolerance_bp?: number;
  auto_detect_length?: boolean;
  min_barcode_score?: number;
  linked_trim?: boolean;
  rev_primer_universal?: string | null;
  normalize_headers?: boolean;
  nb_dirs?: string[];
  /** Keep intermediate raw-read FASTA files after consensus calling. Default false. */
  save_intermediate_reads?: boolean;
  /** MAPQ threshold for alignment filter. Default 25. */
  min_mapq?: number;
  /** Minimum per-position depth for consensus base call. Default 1. */
  min_consensus_depth?: number;
}
