/** TypeScript mirror of the unified MAME Step 3 RPC contract. */

/** Exactly one primary source is required; verdict_xlsx and output_xlsx are required. */
export interface BuildEvolveproInputParams {
  /** Generic long-format .csv, .xlsx, or .xls activity source. */
  activity_path?: string | null
  /** Interpretation of activity_path values. Raw data is WT-normalized per cohort. */
  activity_scale?: "raw" | "relative_to_wt"
  /** Existing pre-normalized, well-labeled GC sheet. Wells are mapped by layout_xlsx, or by the verdict sheet when none is given. */
  gc_data_xlsx?: string | null
  /** Existing raw, well-labeled round-1 Agilent report. Wells are mapped by layout_xlsx, or by the verdict sheet when none is given. */
  round1_report_xlsx?: string | null
  /**
   * Whole-plate raw Agilent report whose sample names are numeric positions
   * (`1`, `2`, `3`, ...). ID `i` is the `i`-th variant of the plate order, so
   * it needs an order source: expected_xlsx or layout_xlsx.
   */
  numeric_report_xlsx?: string | null
  /** Optional variant-labeled raw Agilent confirmation report. */
  remeasure_report_xlsx?: string | null
  /**
   * Optional replicated confirmation whose sample names are numeric positions
   * (`1`, `1-2`, `1-3`, ...). ID `j` is the `j`-th variant the primary screen
   * put above wild-type, in plate order, so it needs an order source too.
   */
  remeasure_numeric_xlsx?: string | null
  /** Mandatory strict NGS evidence workbook. */
  verdict_xlsx: string
  /** Mapping metadata required by well-labeled inputs. */
  layout_xlsx?: string | null
  /**
   * Designed variant list (the analyze step expected workbook). Order source
   * for numeric-ID reports, and the one to prefer: it is the order the run was
   * placed in, with nothing transcribed by hand.
   */
  expected_xlsx?: string | null
  output_xlsx: string
  mismatch_threshold?: number
  /** Optional well-level relative-activity review export for raw round-1 reports. */
  gc_export_xlsx?: string | null
  allow_label_mismatch?: boolean
}

export interface MismatchedVariant {
  variant: string
  authoritative: number
  fallback: number
}

export interface LabelFinding {
  well: string
  expected: string
  observed: string[]
  category: "not_introduced" | "wrong_residue" | "extra_mutation" | "sequence_collapse" | "cross_well"
  verdict: string
}

export interface LabelAudit {
  discordant: LabelFinding[]
  n_checked: number
  n_unevaluable: number
  is_closed_permutation: boolean
  cycles: string[][]
  geometry: "two_swap" | "contiguous_shift" | "scattered" | "global_offset" | null
}

export interface BuildEvolveproInputResult {
  output_path: string
  n_variants: number
  n_authoritative: number
  n_fallback_only: number
  warnings: string[]
  mismatched: MismatchedVariant[]
  n_ngs_excluded: number
  ngs_excluded: string[]
  gc_export_path: string
  label_audit: LabelAudit | null
  manifest_path: string
  primary_format: "activity_path" | "gc_data_xlsx" | "round1_report_xlsx" | "numeric_report_xlsx"
  input_count: number
  evaluable_count: number
  exclusion_reason_counts: Record<string, number>
  normalization_sources: string[]
  evidence_hash: string
  artifact_hashes: Record<string, string>
  /**
   * Wild-type replicates behind this workbook, on the scale of its activity
   * column: each WT measurement over the mean WT of its own cohort, the same
   * division every variant measurement went through.
   *
   * The workbook holds one row per designed variant and the WT rows are
   * filtered out on the way in, so this response is the only route out of the
   * build. Step 4.2 needs them to run the bootstrap behind
   * switch_combinatorial and stop, and reads them back off the round
   * (`Round.evolvepro_input.wt_values`).
   *
   * Empty when the primary source carried no WT rows, which is the
   * pre-normalized GC sheet: its WT mean was taken upstream and the replicates
   * behind it never reach this app.
   */
  wt_values: number[]
}
