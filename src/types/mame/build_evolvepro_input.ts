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
 * Two mutually exclusive input modes, enforced backend-side by _mode_xor:
 *   rank mode   , keyed on gc_data_xlsx (requires layout_xlsx). rep_batch_xlsx
 *                  and prev_evolvepro_xlsx are the optional confirmation pair.
 *   reports mode, keyed on remeasure_report_xlsx plus exactly one round-1
 *                  source: round1_report_xlsx (needs layout_xlsx) or
 *                  round1_evolvepro_xlsx (no layout needed).
 */
export interface BuildEvolveproInputParams {
  /** Plate layout xlsx with Mutant and Well Pos. columns, or the sample map
   *  xlsx with sample_name and well columns. Required for rank
   *  mode and for raw-report reports mode; optional for prev-EVOLVEpro reports
   *  mode, where it only maps variant → well for NGS verdict gating. */
  layout_xlsx?: string | null
  /** Rank mode: pre-normalised GC data xlsx with Sample Name (well) and Area
   *  columns. Its presence selects rank mode. */
  gc_data_xlsx?: string | null
  /** Rank mode: optional Agilent FID1B rep-batch xlsx (numeric base IDs +
   *  replicate suffixes). Provided together with prev_evolvepro_xlsx to upgrade
   *  the result from "provisional" to "confirmed". */
  rep_batch_xlsx?: string | null
  /** Rank mode: optional previous-round EVOLVEpro xlsx (Variant, activity) used
   *  as the rank source for the numeric-ID → variant mapping. */
  prev_evolvepro_xlsx?: string | null
  /** Reports mode: raw Agilent FID1B round-1 report (sample names are well
   *  positions). One of the two round-1 sources; requires layout_xlsx. */
  round1_report_xlsx?: string | null
  /** Reports mode: round-1 baseline already in EVOLVEpro form (Variant,
   *  activity). The other round-1 source; no layout needed. */
  round1_evolvepro_xlsx?: string | null
  /** Reports mode: variant-labeled Agilent FID1B re-measure report. Its
   *  presence selects reports mode. */
  remeasure_report_xlsx?: string | null
  /** Optional NGS verdict xlsx. Variants whose well carries a non-PASS verdict
   *  are excluded. Omit to skip NGS gating. */
  verdict_xlsx?: string | null
  /** Destination xlsx. Parent directory must exist. */
  output_xlsx: string
  /** Mean-difference threshold for the replicate mismatch flag. Default 0.1. */
  mismatch_threshold?: number
  /** Where to write the ID->variant JSON audit. Defaults next to output_xlsx. */
  mapping_audit_path?: string | null
  /** Reports mode, raw round-1 only: where to write the intermediate well-level
   *  relative activity (Sample Name, Area). Omit to skip the export. */
  gc_export_xlsx?: string | null
}

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

/** Result of a mame.activity.build_evolvepro_input RPC call. */
export interface BuildEvolveproInputResult {
  /** Resolved path to the written EVOLVEpro input xlsx. */
  output_path: string
  /** Which input mode the backend actually ran. */
  mode: "rank" | "reports"
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
   * Confidence of the written table:
   *   "provisional" — layout + GC only (1st-round primary screen; no rep-batch
   *                   confirmation and no previous-round rank mapping).
   *   "confirmed"  , rep-batch authoritative replicates merged in.
   * Rank mode only; the backend omits this field in reports mode.
   */
  confidence?: "provisional" | "confirmed"
  /**
   * Variants where the 3-replicate confirmation mean diverged from the
   * 1-replicate primary screen mean beyond the merge threshold (QC, not error).
   */
  mismatched: MismatchedVariant[]
}
