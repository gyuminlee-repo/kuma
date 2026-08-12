/**
 * TypeScript mirror of the `run_quality` block on the analyze response.
 *
 * Keep in sync with:
 *   - kuma_core/mame/run_quality.py (assess_run_quality, serialise_run_quality)
 *   - kuma_core/mame/ingest/flow_cell.py (pore counts, reuse ledger)
 *   - python-core/sidecar_mame/handlers/analyze.py (response assembly)
 */

/**
 * `blocking` means no well cleared the depth its own consensus needs, so every
 * verdict on the screen is an artefact. `warning` means the run stands and
 * something about it should be known before the next one.
 */
export type RunQualitySeverity = "blocking" | "warning"

/** Where a threshold on this block came from, and how much that is worth. */
export type ThresholdKind =
  /** A parameter default in a vendor workflow. Not a specification. */
  | "vendor_default"
  /** Prose in vendor documentation that says "We recommend". */
  | "vendor_recommendation"
  /** A published measurement. */
  | "literature"
  /** A replacement guarantee, which is not an operating limit. */
  | "vendor_warranty"

export interface RunQualityThreshold {
  value?: number
  coverage?: number
  minor_allele_fraction?: number
  source: string
  kind: ThresholdKind
  /** Held pending a calibration of our own. */
  provisional?: boolean
  /** False when the number is reported for scale and never gates anything. */
  enforced?: boolean
}

export interface RunQualityFinding {
  code:
    | "median_depth_below_floor"
    | "median_depth_below_recommended"
    | "flow_cell_reused"
    | "variants_at_reference_edge"
  severity: RunQualitySeverity
  [key: string]: unknown
}

/** The earlier run this project recorded for the same flow cell. */
export interface FlowCellPreviousUse {
  flow_cell_id?: string | null
  product_code?: string | null
  run_dir?: string | null
  started?: string | null
  pore_start?: number | null
  pore_end?: number | null
}

/**
 * One reference position and how the whole plate read it.
 *
 * Nothing here is graded. A position forty wells reported is carried exactly as
 * one two wells reported, and no field on this row is a verdict.
 */
export interface RecurringPosition {
  /** 1-based reference coordinate. */
  position: number
  /**
   * Scored records that reported this position. Replicate plates contribute one
   * record per plate, so this counts scored records, not distinct wells.
   */
  wells: number
  /**
   * Weak-strand share of the minor allele over those records, `min(plus, minus)
   * / (plus + minus)`. Null for all three when no record carried a share, which
   * is UNKNOWN and never the same as 0.0, the reading "one strand only".
   */
  median_weak_strand_share: number | null
  min_weak_strand_share: number | null
  max_weak_strand_share: number | null
  /** How many of `wells` contributed a share, and how many could not. The
   * unknown ones are left out of the statistics above, not entered as 0.0. */
  shares_known: number
  shares_unknown: number
}

/**
 * Which reference positions recur across the wells of one run.
 *
 * A minor allele at one position in one well is a candidate mixture; the same
 * position returning well after well is what a sequence-context artifact looks
 * like, because the context belongs to the amplicon rather than to the clone.
 * Reported with no threshold, exactly like the pore counts above.
 *
 * Every count is a LOWER BOUND (`lower_bound` says so on the block itself):
 * each well contributes at most ten mix-eligible positions ranked by minor
 * fraction, and on both measured runs every single well was truncated, so a
 * position that ranked eleventh in a well is missing from its tally here.
 */
export interface PositionRecurrence {
  /** Always true. The counts below are floors, never a census. */
  lower_bound: boolean
  /** Records that reported at least one mix-eligible position. */
  wells_contributing: number
  /** Of those, how many had their position list truncated. */
  wells_truncated: number
  /** Distinct positions seen at all, before the recurrence restriction. */
  positions_seen: number
  /**
   * Positions exactly one well reported, left out because "recurrence" means
   * more than once. Definitional, not a threshold, and counted rather than
   * silently dropped.
   */
  positions_single_well: number
  /** Most-recurrent first, then by coordinate. Never truncated. */
  positions: RecurringPosition[]
}

/**
 * Whether the run could have produced a scorable plate, read before its
 * verdicts rather than after them.
 *
 * Present on every analyze response, including a clean one, where `severity` is
 * null and `findings` is empty. A block that appeared only for bad runs could
 * not be told apart from an older sidecar that never graded one.
 */
export interface RunQuality {
  severity: RunQualitySeverity | null
  /**
   * Median reads over the wells this run SCORED. A declared selection has
   * already removed the wells the campaign left empty, so their leaked reads do
   * not drag this down.
   */
  median_well_reads: number | null
  /** The floor in force, below which a well fails consensus QC. */
  min_read_count: number | null
  /** Null when either number is missing, which is not the same as passing. */
  depth_ok: boolean | null
  wells_under_floor: number
  wells_total: number
  /** The depth the vendor recommends aiming for, reported as a target. */
  recommended_reads: number
  flow_cell_id: string | null
  /** Pores at the first and last mux scan of the run. */
  pore_start: number | null
  pore_end: number | null
  /**
   * The vendor warranty figure, carried as context. Deliberately not a gate:
   * one of these runs started at 343 pores and returned 515 reads a well.
   */
  pore_warranty_min: number
  reused_from: FlowCellPreviousUse | null
  /**
   * Expected mutations whose codon sits within `edge_margin_bp` of an end of
   * the reference that was aligned against, on a run that used the supplied
   * reference unmodified. Empty whenever an amplicon was extracted, which is
   * the ordinary case, and empty on results from before v0.16.21.
   */
  edge_variants?: string[]
  edge_margin_bp?: number
  thresholds: Record<string, RunQualityThreshold>
  findings: RunQualityFinding[]
  /**
   * Optional because a result saved by a sidecar that predates the tally has no
   * such block, and an absent tally must not read as a plate on which nothing
   * recurred. Carried on the response and into the store; nothing renders it
   * yet.
   */
  position_recurrence?: PositionRecurrence
}
