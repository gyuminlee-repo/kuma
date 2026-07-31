/**
 * TypeScript mirror of the ``mame.activity.build_evolvepro_input`` RPC handler.
 *
 * Keep in sync with:
 *   - kuma_core/mame/activity/build_evolvepro_input.py (build_evolvepro_input)
 *   - python-core/sidecar_mame/handlers/activity.py (handle_build_evolvepro_input)
 *   - python-core/sidecar_mame/models.py (BuildEvolveproInputParams)
 */

/**
 * Parameters for the mame.activity.build_evolvepro_input RPC method.
 *
 * Two independent input axes, enforced backend-side by _axis_sources:
 *   axis A, the 1-replicate primary screen. Exactly one of round1_report_xlsx
 *           (raw report, well labels, needs layout_xlsx), gc_data_xlsx
 *           (pre-normalised GC sheet, well labels, needs layout_xlsx) or
 *           round1_evolvepro_xlsx (previous EVOLVEpro file, variant labels).
 *   axis B, the n-replicate confirmation. At most one of remeasure_report_xlsx
 *           (variant labels) or rep_batch_xlsx (numeric index, which requires
 *           prev_evolvepro_xlsx as its rank source). Omitting axis B yields a
 *           provisional build.
 * The axes do not constrain each other, so every A/B pair is accepted.
 */
export interface BuildEvolveproInputParams {
  /** Plate layout xlsx with Mutant and Well Pos. columns, or the sample map
   *  xlsx with sample_name and well columns. Required for rank
   *  mode and for raw-report reports mode; optional for prev-EVOLVEpro reports
   *  mode, where it only maps variant → well for NGS verdict gating. */
  layout_xlsx?: string | null
  /** Axis A: pre-normalised GC data xlsx with Sample Name (well) and Area
   *  columns. Requires layout_xlsx. */
  gc_data_xlsx?: string | null
  /** Axis B: Agilent FID1B rep-batch xlsx (numeric base IDs + replicate
   *  suffixes). Requires prev_evolvepro_xlsx as its rank source. */
  rep_batch_xlsx?: string | null
  /** Axis B: previous-round EVOLVEpro xlsx (Variant, activity) used as the rank
   *  source for the numeric-ID to variant mapping. Only valid with
   *  rep_batch_xlsx; for a previous-round baseline use round1_evolvepro_xlsx. */
  prev_evolvepro_xlsx?: string | null
  /** Axis A: raw Agilent FID1B primary screen report (sample names are well
   *  positions). Requires layout_xlsx. */
  round1_report_xlsx?: string | null
  /** Axis A: primary screen baseline already in EVOLVEpro form (Variant,
   *  activity). No layout needed. */
  round1_evolvepro_xlsx?: string | null
  /** Axis A: whole-plate primary screen whose sample names are bare numeric
   *  IDs. Needs an order source: expected_mutations_xlsx or layout_xlsx. */
  round1_rep_batch_xlsx?: string | null
  /** Order source for the numeric primary screen: the KURO expected_mutations
   *  sheet. Preferred over layout_xlsx, which is transcribed by hand. */
  expected_mutations_xlsx?: string | null
  /** Axis B: variant-labeled Agilent FID1B confirmation report. */
  remeasure_report_xlsx?: string | null
  /** Axis B: confirmation whose numeric IDs index the above-WT subset of the
   *  numeric primary screen. Requires round1_rep_batch_xlsx. */
  remeasure_rep_batch_xlsx?: string | null
  /** Optional NGS verdict xlsx. Variants whose well carries a non-PASS verdict
   *  are excluded. Omit to skip NGS gating. */
  verdict_xlsx?: string | null
  /** Destination xlsx. Parent directory must exist. */
  output_xlsx: string
  /** Mean-difference threshold for the replicate mismatch flag. Default 0.1. */
  mismatch_threshold?: number
  /** Where to write the ID->variant JSON audit. Defaults next to output_xlsx. */
  mapping_audit_path?: string | null
  /** Raw primary screen report only: where to write the intermediate well-level
   *  relative activity (Sample Name, Area). Omit to skip the export. */
  gc_export_xlsx?: string | null
  /** When false (default), a closed-permutation well<->well label swap (label
   *  audit) or a severity="error" numeric-index label-swap warning aborts the
   *  build with a ValueError before anything is written. Set true to proceed
   *  once the flagged wells/variants have been reviewed. */
  allow_label_mismatch?: boolean
}

/**
 * Axis A identifier reported back by the backend (the PRIMARY_* constants in
 * kuma_core/mame/activity/build_evolvepro_input.py).
 */
export type BuildEvolveproPrimarySourceId =
  | "raw_report"
  | "gc_sheet"
  | "prev_evolvepro"
  | "numeric_report"

/**
 * Axis B identifier reported back by the backend (the CONFIRM_* constants).
 * "none" means no confirmation input, so the table is provisional.
 */
export type BuildEvolveproConfirmationSourceId =
  | "variant_labels"
  | "numeric_subset"
  | "numeric_index"
  | "none"

/** One ID->variant assignment plus its layout well, for the audit table. */
export interface MappingAuditRow {
  /** 1-based numeric base ID from the Agilent rep-batch report. */
  id: number
  /** Short EVOLVEpro variant assigned to that ID by previous-round rank. */
  variant: string
  /** Layout well for the variant, when present in the plate layout. */
  well: string | null
}

/** A single label-swap warning surfaced by the build pipeline. */
export interface SwapWarning {
  severity: "error" | "warning"
  code: "label_swap_cycle" | "value_collision" | "layout_orphan"
  variants: string[]
  wells: string[]
  values: number[]
  message: string
}

/**
 * One variant whose authoritative (3-replicate confirmation) mean diverged
 * from the fallback (1-replicate primary screen) mean beyond the merge
 * threshold. Informational QC, not an error.
 */
export interface MismatchedVariant {
  /** Short EVOLVEpro variant label. */
  variant: string
  /** Authoritative replicate-report mean (the value written to the output). */
  authoritative: number
  /** Fallback GC-data primary-screen mean. */
  fallback: number
}

/**
 * One well's label-audit outcome (only populated for discordant wells).
 * Mirrors kuma_core.mame.activity.label_audit.LabelFinding.
 */
export interface LabelFinding {
  well: string
  expected: string
  observed: string[]
  category:
    | "not_introduced"
    | "wrong_residue"
    | "extra_mutation"
    | "sequence_collapse"
    | "cross_well"
  verdict: string
}

/**
 * Plate-level well<->mutant label-audit result. Mirrors
 * kuma_core.mame.activity.label_audit.LabelAudit. Requires both verdict_xlsx
 * and layout_xlsx; null on the response when either is omitted.
 */
export interface LabelAudit {
  discordant: LabelFinding[]
  n_checked: number
  n_unevaluable: number
  is_closed_permutation: boolean
  cycles: string[][]
  geometry: "two_swap" | "contiguous_shift" | "scattered" | "global_offset" | null
}

/** Result of a mame.activity.build_evolvepro_input RPC call. */
export interface BuildEvolveproInputResult {
  /** Resolved path to the written EVOLVEpro input xlsx. */
  output_path: string
  /** Which input mode the backend actually ran. Legacy two-way label; prefer
   *  primary_source / confirmation_source, which name the axis pair exactly. */
  mode: "rank" | "reports"
  /** Axis A source that supplied the 1-replicate primary screen baseline. */
  primary_source: BuildEvolveproPrimarySourceId
  /** Axis B source whose n-replicate means overrode the baseline, or "none". */
  confirmation_source: BuildEvolveproConfirmationSourceId
  /** Total variants written to the output file. */
  n_variants: number
  /** Variants sourced from the authoritative rep-batch report. */
  n_authoritative: number
  /** Variants present only in the GC fallback source. */
  n_fallback_only: number
  /** ID->variant mapping table (human veto artifact, also written as JSON). */
  mapping_audit: MappingAuditRow[]
  /** Resolved path to the mapping audit JSON file. Empty string in reports
   *  mode, where no JSON audit artifact is written. */
  mapping_audit_path: string
  /** Variants dropped because their layout well carried a non-PASS NGS verdict.
   *  Always 0 in rank mode. */
  n_ngs_excluded: number
  /** Short variant labels behind n_ngs_excluded. Empty in rank mode. */
  ngs_excluded: string[]
  /** Resolved path to the well-level relative activity export. Empty string
   *  when none was requested, and always empty in rank mode. */
  gc_export_path?: string
  /**
   * Whether the previous EVOLVEpro file rows were in non-increasing activity
   * order. False is a veto signal that the rank assumption may not hold.
   */
  prev_descending: boolean
  /** Human-readable warnings (excluded wells, rank coverage gaps). */
  warnings: string[]
  /** Label-swap warnings comparing merged activity against the previous file. */
  swap_warnings: SwapWarning[]
  /**
   * Confidence of the written table, rank mode only (the backend omits it on
   * the other axis pairs). Derive the badge from confirmation_source instead:
   * "none" is provisional on every primary source.
   */
  confidence?: "provisional" | "confirmed"
  /**
   * Variants where the 3-replicate confirmation mean diverged from the
   * 1-replicate primary screen mean beyond the merge threshold (QC, not error).
   */
  mismatched: MismatchedVariant[]
  /** Well<->mutant discordance audit; null unless both verdict_xlsx and
   *  layout_xlsx were supplied. */
  label_audit?: LabelAudit | null
}
