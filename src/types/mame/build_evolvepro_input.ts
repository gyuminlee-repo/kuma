/**
 * TypeScript mirror of the ``mame.activity.build_evolvepro_input`` RPC handler.
 *
 * Keep in sync with:
 *   - kuma_core/mame/activity/build_evolvepro_input.py (build_evolvepro_input)
 *   - python-core/sidecar_mame/handlers/activity.py (handle_build_evolvepro_input)
 *   - python-core/sidecar_mame/models.py (BuildEvolveproInputParams)
 */

/** Parameters for the mame.activity.build_evolvepro_input RPC method. */
export interface BuildEvolveproInputParams {
  /** Plate layout xlsx with Mutant and Well Pos. columns. */
  layout_xlsx: string
  /** Pre-normalised GC data xlsx with Sample Name (well) and Area columns. */
  gc_data_xlsx: string
  /** Optional Agilent FID1B rep-batch xlsx (numeric base IDs + replicate
   *  suffixes). Provided together with prev_evolvepro_xlsx to upgrade the
   *  result from "provisional" to "confirmed". */
  rep_batch_xlsx?: string | null
  /** Optional previous-round EVOLVEpro xlsx (Variant, activity) used as the
   *  rank source for the numeric-ID → variant mapping (confirmation step). */
  prev_evolvepro_xlsx?: string | null
  /** Destination xlsx. Parent directory must exist. */
  output_xlsx: string
  /** Mean-difference threshold for the replicate mismatch flag. Default 0.1. */
  mismatch_threshold?: number
  /** Where to write the ID->variant JSON audit. Defaults next to output_xlsx. */
  mapping_audit_path?: string | null
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
  /** Total variants written to the output file. */
  n_variants: number
  /** Variants sourced from the authoritative rep-batch report. */
  n_authoritative: number
  /** Variants present only in the GC fallback source. */
  n_fallback_only: number
  /** ID->variant mapping table (human veto artifact, also written as JSON). */
  mapping_audit: MappingAuditRow[]
  /** Resolved path to the mapping audit JSON file. */
  mapping_audit_path: string
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
   *   "confirmed"   — rep-batch authoritative replicates merged in.
   */
  confidence: "provisional" | "confirmed"
  /**
   * Variants where the 3-replicate confirmation mean diverged from the
   * 1-replicate primary screen mean beyond the merge threshold (QC, not error).
   */
  mismatched: MismatchedVariant[]
}
