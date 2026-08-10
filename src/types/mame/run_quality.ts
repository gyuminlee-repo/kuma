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
  thresholds: Record<string, RunQualityThreshold>
  findings: RunQualityFinding[]
}
