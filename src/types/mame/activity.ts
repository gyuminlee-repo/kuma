/**
 * TypeScript mirror of kuma_core/mame/activity/models.py Pydantic models.
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.3
 *
 * Keep in sync with:
 *   - kuma_core/mame/activity/models.py (Pydantic)
 *   - fixtures/activity_demo/generate.py (ActivityRecord columns)
 */

export interface PlateConfig {
  plate_id: string
  wt_wells: string[]
  control_wells: string[]
}

export interface PlateMeta {
  plates: PlateConfig[]
}

export interface ActivityRecord {
  plate_id: string
  well_id: string
  value: number
  replicate_idx: number
  is_wt: boolean
  source_file: string
}

export interface ActivityTable {
  records: ActivityRecord[]
  plate_meta: PlateMeta
}

export interface MergedRow {
  plate_id: string
  well_id: string
  mutation: string | null
  mutation_source: "kuro_design" | "mame_genotype" | "activity_only"
  expected_mutation: string | null
  called_mutation: string | null
  ngs_success: boolean
  activity_raw_mean: number | null
  activity_raw_sd: number | null
  activity_replicates: number[]
  replicate_n: number
  fold_change: number | null
  log2_fc: number | null
  /** Phase A adapter output from compute_relative_activity. undefined = not yet computed. */
  relative_activity?: number | null
}

// B-4 models.py SwapWarning mirror
export interface SwapWarning {
  severity: "error" | "warning"
  code: "label_swap_cycle" | "value_collision" | "layout_orphan"
  variants: string[]
  wells: string[]
  values: number[]
  message: string
}

// B-4 MergeReplicatesStats mirror
export interface MergeReplicatesStats {
  authoritative_count: number
  fallback_count: number
  merged_count: number
  mismatched: string[]  // Variant[]
}

export interface MergeStats {
  n_total_wells: number
  n_with_activity: number
  n_with_genotype: number
  n_ngs_success: number
  n_wt: number
  n_duplicate_warnings: number
  n_excluded_from_export: number
  /** B-4 addition: label-swap warnings. Empty array = no warnings. Optional for backward compat. */
  warnings?: SwapWarning[]
}

// Phase A adapter result mirrors
export interface AgilentRecord {
  sample_name: string
  area: number
  is_wt: boolean
  replicate_n: number
  is_relative: false
}

export interface RelativeActivityRecord {
  sample_name: string
  area: number
  is_relative: true
}
