/** TypeScript mirror of the unified MAME Step 3 RPC contract. */
import type { ResequenceEvidence } from "./resequence";

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
  /** Optional well- or variant-labeled raw Agilent confirmation report (A1, A1-1, S11I-1). Wells use layout_xlsx or verdict_xlsx mapping. */
  remeasure_report_xlsx?: string | null
  /**
   * Optional replicated confirmation whose sample names are numeric positions
   * (`1`, `1-2`, `1-3`, ...). ID `j` is the `j`-th variant the primary screen
   * put above wild-type, in plate order, so it needs an order source too.
   */
  remeasure_numeric_xlsx?: string | null
  /**
   * Optional replicated confirmation whose sample names are wells
   * (`A1-1`, `A1-2`, ...; a bare `A1` is replicate 1). Wells map to variants as
   * the well-labeled primaries do, and each area is divided by the mean of the
   * WT well plus any `WT<n>` rows, so the report needs no WT block. Sample names
   * that are not wells are skipped with a warning. At most one of the three
   * confirmation fields may be set.
   */
  remeasure_well_xlsx?: string | null
  /** Mandatory strict NGS evidence workbook. */
  verdict_xlsx: string
  resequence_evidence?: ResequenceEvidence | null
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
  /**
   * GC rows the operator left out after reviewing them, each as it read then.
   * The build refuses when that position no longer holds the same name and
   * area. Mirrors `ExcludedGcRow` in `python-core/sidecar_mame/models.py`.
   */
  excluded_rows?: ExcludedGcRow[]
}

/** Input fields that hold a GC file. */
export type GcSourceField =
  | "activity_path"
  | "gc_data_xlsx"
  | "round1_report_xlsx"
  | "numeric_report_xlsx"
  | "remeasure_report_xlsx"
  | "remeasure_numeric_xlsx"
  | "remeasure_well_xlsx"

/** Where a GC row sits: 1-based sheet row, 1-based FID1B block or null for a flat sheet. */
export interface GcRowPosition {
  source: GcSourceField
  row_index: number
  block_index: number | null
  sample_name: string
  area: number | null
}

export interface ExcludedGcRow {
  source: GcSourceField
  row_index: number
  block_index?: number | null
  sample_name: string
  area?: number | null
}

/**
 * A GC row a reader set aside, or flagged and kept (`kept`). `reason` is one
 * of the `exclusion_reason_counts` keys: non_well_sample, unrecognized_sample,
 * numeric_calibration, no_area, no_name, unmapped_well, unmapped_variant,
 * operator_excluded, duplicate_replicate, duplicate_well.
 */
export interface ReportedGcRow extends GcRowPosition {
  reason: string
  kept: boolean
}

/**
 * `mame.activity.preview_gc_rows` request: the build's own sources, mapping and
 * evidence. Mirrors `PreviewGcRowsParams` (python-core/sidecar_mame/models.py),
 * which shares the build's validation, so the preview refuses what the build
 * refuses. `excluded_rows` is the operator's selection, which the build's own
 * checks judge into `selection_refusal`.
 */
export type PreviewGcRowsParams = Omit<
  BuildEvolveproInputParams,
  "output_xlsx" | "gc_export_xlsx" | "mismatch_threshold" | "allow_label_mismatch"
>

/**
 * What the build does with a row. `used` and `wt` rows enter the build and an
 * operator may leave them out; every other status is the reader's own call:
 * `set_aside` (no membership, `reason` says why), `ignored` (passed over, a
 * declared WT well in a one-replicate report), `locked` (this run's row in the
 * other notation, which refuses the build however it is ticked) and
 * `unjudged` (the build refused the files before reaching the row).
 */
export type GcRowStatus = "used" | "wt" | "set_aside" | "ignored" | "locked" | "unjudged"

export const GC_ROW_STATUSES: readonly GcRowStatus[] = [
  "used", "wt", "set_aside", "ignored", "locked", "unjudged",
]

export interface PreviewGcRow {
  source: GcSourceField
  block_index: number | null
  row_index: number
  sample_name: string
  area: number | null
  /** What the name is in this field (gc_sample classify_sample kind). */
  kind: string
  status: GcRowStatus
  /** Exclusion reason, ignored detail, or `other_notation` for a locked row. */
  reason: string | null
  /** The refusal sentence for a locked row; empty otherwise. */
  detail: string
  /** `duplicate_replicate` / `duplicate_well`: kept in use but suspicious. */
  flags: string[]
}

export interface PreviewGcRowsResult {
  rows: PreviewGcRow[]
  /** Why the build would refuse these files as given, or null. */
  refusal: string | null
  /**
   * The refusal the build gives with the sent `excluded_rows`, when that
   * selection is what causes it; null otherwise. `rows` and `refusal` state
   * the defaults before any exclusion.
   */
  selection_refusal: string | null
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

/** Every primary source `build_evolvepro_input` accepts; its name becomes `primary_format`. */
export const BUILD_EVOLVEPRO_PRIMARY_FORMATS = [
  "activity_path",
  "gc_data_xlsx",
  "round1_report_xlsx",
  "numeric_report_xlsx",
] as const;
export type BuildEvolveproPrimaryFormat = typeof BUILD_EVOLVEPRO_PRIMARY_FORMATS[number];

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
  primary_format: BuildEvolveproPrimaryFormat
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

  /**
   * The replicates behind each exported activity, keyed by the variant as the
   * workbook writes it, on the scale of the activity column.
   *
   * The workbook states one mean per variant and nothing about how many
   * measurements produced it, so a reader cannot tell a value measured once
   * from a value measured four times. Those carry different weight in any
   * judgement about whether a round improved beyond measurement noise.
   *
   * Lists rather than counts: the build already held these and kept only the
   * mean, which is what made this gap, and summarising again here would make
   * the next one.
   */
  variant_replicates: Record<string, number[]>

  /** Every GC row a reader set aside or flagged, with its position and reason. */
  excluded_rows: ReportedGcRow[]

  /**
   * The WT rows each reference was divided by. A shared GC run can carry
   * another experiment's WT under the same name, so the rows are stated.
   */
  wt_rows: GcRowPosition[]
}
