/** TypeScript interfaces for EvolveProprimer JSON-RPC communication. */

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

export interface SdmPrimerResult {
  mutation: string;
  aa_position: number;
  codon_pos: number;
  forward_seq: string;
  reverse_seq: string;
  fwd_len: number;
  rev_len: number;
  overlap_len: number;
  tm_no_fwd: number;
  tm_no_rev: number;
  tm_overlap: number;
  tm_condition_met: boolean;
  tolerance_used: number;
  has_offtarget: boolean;
  penalty: number;
  gc_fwd: number;
  gc_rev: number;
  wt_codon: string;
  mt_codon: string;
  overlap_seq: string;
  warnings: string[];
}

export interface EvolveproLoadResult {
  variants: string[];
  y_preds: number[];
  total_count: number;
  selected_count: number;
}

export interface DesignResult {
  results: SdmPrimerResult[];
  success_count: number;
  total_count: number;
  failed_mutations: string[];
}

export interface PlateMapping {
  well: string;
  primer_name: string;
  sequence: string;
  primer_type: "forward" | "reverse";
  mutation: string;
}

export interface PlateMapResult {
  mappings: PlateMapping[];
  dedup_info: Record<string, string[]>;
}

export interface ExportResult {
  success: boolean;
  filepath: string;
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
