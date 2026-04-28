import type { ReactNode } from "react";

export type VerdictClass =
  | "PASS"
  | "AMBIGUOUS"
  | "FRAMESHIFT"
  | "MANY"
  | "LOWDEPTH"
  | "WRONG_AA";

export type SidecarStatus = "disconnected" | "connecting" | "ready" | "error";

export interface VerdictRecord {
  native_barcode: string;
  custom_barcode: string;
  file_size_kb: number;
  source_path: string;
  aa_sequence: string;
  observed_nt_changes: string[];
  observed_aa_changes: string[];
  expected_mutations: string[];
  verdict: VerdictClass;
  verdict_notes: string;
}

export interface ReplicateResult {
  mutant_id: string;
  selected_plate: string | null;
  selection_reason: string;
  failed: boolean;
  plate_keys: string[];
}

export interface AnalyzeSummary {
  total: number;
  pass_count: number;
  ambiguous_count: number;
  fail_count: number;
}

export interface AnalyzeResult {
  verdicts: VerdictRecord[];
  replicates: ReplicateResult[];
  output_path: string;
  summary: AnalyzeSummary;
}

export interface WellEntry {
  well: string;
  barcode: string;
  native_barcode: string;
  verdict: VerdictClass;
  mutant_id: string;
  selected: boolean;
  notes: string;
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
  many_cutoff: number;
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

export interface PlateDataResult {
  wells: WellEntry[];
}

export interface ScreenTab {
  id: "input" | "verdict" | "plate" | "export";
  label: string;
  content?: ReactNode;
}
