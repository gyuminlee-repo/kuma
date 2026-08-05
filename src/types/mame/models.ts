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

/**
 * Demux yield reported by the analyze response. Raw-run mode only: the handler
 * derives every field from the demux it just ran and omits the keys entirely in
 * consensus-dir mode (`python-core/sidecar_mame/handlers/analyze.py`, raw-run
 * branch). Absent fields must stay absent in the UI rather than be defaulted to
 * a number, so a zero-result explanation never shows a count the backend did
 * not report: a 0 would read as "every read was rejected", the opposite of
 * "this mode never counted".
 *
 * The three gate counters narrow a zero-verdict run to a cause, and only in
 * combination (`DemuxStats` names, kept verbatim):
 *   total_reads      reads read out of `fastq_pass/`
 *   passed_mapq      reads that cleared the MAPQ gate; 0 against a non-zero
 *                    total_reads is the signature of a mismatched reference
 *   passed_coverage  of those, the reads that also cleared the coverage gate;
 *                    0 against a non-zero passed_mapq is the signature of a
 *                    whole-construct reference met with amplicon reads
 */
export interface AnalyzeYield {
  assigned_reads?: number;
  wells_with_reads?: number;
  total_reads?: number;
  passed_mapq?: number;
  passed_coverage?: number;
}

export interface AnalyzeResult extends AnalyzeYield {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  output_path: string;
  summary: AnalyzeSummary;
  distribution_stats: DistributionStats;
  reference_resolution?: {
    readonly path: string;
    readonly extracted: boolean;
    readonly span_start: number | null;
    readonly span_end: number | null;
    readonly original_length: number;
    readonly cds_start: number;
    readonly cds_end: number;
    readonly note: string;
  };
  /**
   * What became of the pick list this run wrote beside its workbook.
   * Optional on the type because a snapshot persisted before the field existed
   * is replayed verbatim; a live sidecar always sends it.
   */
  janus_autosave?: JanusAutosaveResult;
  /**
   * What became of the instrument (9-column) mapping the same run wrote. Same
   * shape, same optionality, different file: `..._janus.csv` next to
   * `..._picks.csv`.
   */
  janus_mapping_autosave?: JanusAutosaveResult;
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

/**
 * Does an expected workbook agree with its own primer plate sheet?
 *
 * Wire shape of `plate_order_payload` in
 * `python-core/sidecar_mame/handlers/barcode_package.py`, returned as-is by the
 * `check_plate_order` RPC. `examples` carries at most 5 disagreeing wells.
 */
export interface PlateOrderReport {
  comparable: boolean;
  mismatched: boolean;
  /** "Fwd List" | "Fwd Plate"; null when the check found no plate sheet. */
  plate_sheet: string | null;
  examples: { well: string; plate: string; expected: string }[];
  missing_from_expected: string[];
  absent_from_plate: string[];
}

/**
 * How much a plate disagreement costs on the run being set up.
 *
 * - "blocking": the layout is inferred from `expected_mutations`, so the sheet
 *   order *is* the well coordinate system and every verdict lands on the wrong
 *   well. Counts and verdicts still look normal, which is why this gates.
 * - "info": a sample map or a confirmed well layout supplies the coordinates,
 *   so the sheet order never reaches a well. The workbook still contradicts
 *   itself, but this run is unaffected.
 */
export type PlateOrderSeverity = "blocking" | "info";

/**
 * A `PlateOrderReport` graded against the layout inputs of the current run.
 *
 * `validate_inputs` grades it server-side (`_plate_order_finding` in
 * `python-core/sidecar_mame/handlers/analyze.py`); the frontend applies the same
 * rule to the ungraded `check_plate_order` response and to layout inputs chosen
 * after a validation.
 */
export interface PlateOrderFinding extends PlateOrderReport {
  severity: PlateOrderSeverity;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  /**
   * Present only when there is something to report: the workbook could be
   * compared and its sheets disagree. `valid` deliberately stays true, so the
   * blocking gate is the frontend's job (see `selectPlateOrderSeverity`).
   */
  plate_order?: PlateOrderFinding;
}

export interface ExportResult {
  output_path: string;
}

export type JanusExportFormat = "csv" | "xlsx";

/**
 * Destination-well assignment strategy for the Janus mapping export.
 *
 * - "compact" (default): dest_well is assigned sequentially from A1 in priority
 *   order, leaving no gaps on the destination plate. A cell stock plate is a
 *   new plate, so filling it from the front is the normal case.
 * - "source": dest_well mirrors the source plate position.
 *
 * Mirrors the ``dest_layout`` param of the ``export_janus_mapping`` RPC
 * (python-core/sidecar_mame/handlers/export.py).
 */
export type JanusDestLayout = "source" | "compact";

/**
 * Column set written to the file.
 *
 * - "device9" (default): the instrument-native worksheet columns transcribed
 *   from the workbook the lab imports (`name | type | Dsp. Rack | no |
 *   Asp. Rack | Asp. Posi | Dsp. Rack | Dsp. Posi | volume`).
 * - "legacy5": the kuma-internal columns (`name | source_plate | source_well |
 *   dest_well | priority_score`).
 */
export type JanusOutputSchema = "device9" | "legacy5";

/**
 * Rack numbers of the source plates on the deck, keyed by the plate label the
 * export writes (`nb_label`: "sort_barcode07" -> "NB07"), so a key is looked up
 * with the same string the row carries. The dialog builds the fields from the
 * preview rows for that reason.
 *
 * Assumption, editable in the dialog: source plates come first in the labware
 * order of the lab workbook `layout` sheet, with the destination plate last.
 */
export type JanusSourceRacks = Record<string, number>;

/**
 * Everything both the export and the preview resolve their behaviour from.
 *
 * Mirrors ``JanusSettings`` (kuma_core/mame/export/janus_mapping.py). The RPC
 * layer takes the same fields in snake_case; `src/lib/mame/janus.ts` does the
 * conversion in one place so the two calls cannot drift.
 */
export interface JanusExportSettings {
  destLayout: JanusDestLayout;
  /** Verdict classes to keep. Default: PASS only. */
  includeVerdicts: VerdictClass[];
  /** Keep fallback picks (off by default: a fallback pick is not verified). */
  includeFallback: boolean;
  outputSchema: JanusOutputSchema;
  /** Dispense volume in µL (device9 only). */
  volume: number;
  /** `type` column value (device9 only). */
  sampleType: string;
  /**
   * Liquid class string (device9 only). No default, and blank does not block:
   * the column ships empty and the preview warns.
   */
  liquidClass: string;
  /**
   * Operator overrides only. An empty map lets the sidecar derive the numbers
   * from the plates of the run, which is what the shipped default does.
   */
  sourceRacks: JanusSourceRacks;
  /** `null` derives it as one past the last source rack. */
  destRack: number | null;
}

/** Resolved settings echoed back by the sidecar, in RPC (snake_case) form. */
export interface JanusResolvedSettings {
  dest_layout: JanusDestLayout;
  include_verdicts: VerdictClass[];
  include_fallback: boolean;
  output_schema: JanusOutputSchema;
  volume: number;
  sample_type: string;
  liquid_class: string;
  /** The operator's overrides, echoed back unchanged. */
  source_racks: JanusSourceRacks;
  /** The operator's override, echoed back unchanged; `null` means derived. */
  dest_rack: number | null;
  /** Header of the file this policy writes, in order. */
  columns: string[];
  /** The deck the file carries: overrides applied on top of the derived numbers. */
  resolved_source_racks?: JanusSourceRacks;
  resolved_dest_rack?: number;
}

/**
 * Why a clone was left out of the pick.
 *
 * - "failed": the picker marked the replicate failed.
 * - "no_selection": no plate was selected.
 * - "missing_verdict": the selected plate carries no verdict record.
 * - "verdict_class": the verdict is outside `includeVerdicts`.
 * - "fallback": the pick is a fallback and `includeFallback` is off.
 */
export type JanusExclusionReason =
  | "failed"
  | "no_selection"
  | "missing_verdict"
  | "verdict_class"
  | "fallback";

export interface JanusExcludedEntry {
  mutant_id: string;
  reason: JanusExclusionReason;
  /** Verdict of the selected plate; empty when no plate was selected. */
  verdict: VerdictClass | "";
  /** Plate label (`nb_label`, e.g. "NB07"); empty when no plate was selected. */
  selected_plate: string;
  is_fallback: boolean;
}

export interface JanusExportResult {
  output_path: string;
  format: JanusExportFormat;
  row_count: number;
  excluded: JanusExcludedEntry[];
  excluded_count: number;
  /** What the written file left blank or derived. */
  warnings: JanusPreviewError[];
  settings: JanusResolvedSettings;
}

/** One row of the Janus mapping, exactly as it is written to the export file. */
export interface JanusPreviewRow {
  name: string;
  source_plate: string;
  source_well: string;
  dest_well: string;
  priority_score: number;
}

/**
 * Validation problem codes returned by the dry-run preview.
 *
 * Mirrors the ``code`` field of ``build_janus_preview_rows``
 * (kuma_core/mame/export/janus_mapping.py).
 */
export type JanusPreviewErrorCode =
  | "unresolved_well"
  | "plate_capacity"
  | "duplicate_dest_well"
  | "missing_liquid_class"
  | "derived_source_rack"
  | "autosave_failed";

/**
 * "error" withholds the file; "warning" names a value that shipped blank or
 * derived, which is never a reason to produce no file.
 */
export type JanusFindingSeverity = "error" | "warning";

export interface JanusPreviewError {
  code: JanusPreviewErrorCode;
  severity: JanusFindingSeverity;
  message: string;
  mutant_ids: string[];
}

/**
 * Result of the ``export_janus_mapping_dry_run`` RPC.
 *
 * The export path fails fast on the same three problems; the preview collects
 * them so every problem is visible before a file is written.
 */
export interface JanusPreviewResult {
  rows: JanusPreviewRow[];
  /** Blocks the export. */
  errors: JanusPreviewError[];
  /** Never blocks: what shipped blank (liquid class) or derived (rack numbers). */
  warnings: JanusPreviewError[];
  row_count: number;
  /** Clones left out of the pick, with the reason for each. */
  excluded: JanusExcludedEntry[];
  excluded_count: number;
  /** The policy these rows were built with, echoed back for display. */
  settings: JanusResolvedSettings;
}

/**
 * Outcome of the Janus mapping written automatically at the end of an analyze.
 *
 * Mirrors ``_autosave_janus_mapping`` in
 * `python-core/sidecar_mame/handlers/analyze.py`, which never raises: a mapping
 * that could not be written is a fact to report, not a reason to lose the run.
 *
 * - "saved": the file exists at `output_path` and carries `row_count` rows.
 * - "skipped": nothing was selected, so no file was written (an empty mapping
 *   reads like a finished plate).
 * - "failed": `errors` says why.
 *
 * `warnings` never changes the status: a blank liquid class and rack numbers
 * derived from the run are reported, not enforced.
 */
export interface JanusAutosaveResult {
  status: "saved" | "skipped" | "failed";
  output_path: string | null;
  format: "csv";
  row_count: number;
  excluded: JanusExcludedEntry[];
  excluded_count: number;
  errors: JanusPreviewError[];
  warnings: JanusPreviewError[];
}

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
  /** Outcome of the cross-talk check itself. An empty candidate list means "no
   *  anomalies" only when this is "ok". Optional for payloads written before the
   *  field existed (treated as "ok"). */
  cross_talk_status?: "not_run" | "insufficient_data" | "ok";

  recovered_mutants: number | null;
  total_mutants: number | null;
  recovery_rate: number | null;
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
