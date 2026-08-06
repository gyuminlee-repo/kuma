/**
 * TypeScript mirror of the ``mame.build_well_layout`` RPC handler and the
 * ``analyze`` ``well_layout`` parameter.
 *
 * Keep in sync with:
 *   - kuma_core/mame/layout.py (build_draft_layout)
 *   - python-core/sidecar_mame/handlers/build_well_layout.py (response dict)
 *   - python-core/sidecar_mame/models.py (BuildWellLayoutParams)
 *   - python-core/sidecar_mame/handlers/analyze.py (well_layout param)
 */

/** Parameters for the mame.build_well_layout RPC method. */
export interface BuildWellLayoutParams {
  /** Path to a KURO results xlsx containing an expected_mutations sheet. */
  expected_mutations_xlsx: string
}

/** A single draft layout row: a well coordinate mapped to a sample name. */
export interface WellLayoutRow {
  /** Well coordinate from seq_to_well (e.g. "A1"); not zero-padded. */
  well: string
  /** Sample name: a mutant_id, or "WT" for the control well. */
  sample: string
}

/** Result of a mame.build_well_layout RPC call. */
export interface BuildWellLayoutResult {
  /**
   * Draft layout rows in column-major order, with the WT control at the
   * ordinal the source stated and last when it stated none. Empty when the set
   * does not fit one plate.
   */
  draft: WellLayoutRow[]
  /** Number of draft rows (mutant wells plus the one WT well). */
  count: number
  /**
   * mutant_id values that do not fit alongside the WT control, so more than 95
   * mutants. The combinatorial barcode space is 12 fwd x 8 rev, so a 97th well
   * cannot be told apart in the reads. One analyze run scores one plate; native
   * barcodes are replicates of that plate, so larger campaigns are split across
   * plates and run one plate at a time, with one layout per plate. Non-empty
   * means nothing was placed.
   */
  dropped_mutant_ids: string[]
}

/**
 * well_id -> sample_name override consumed by the analyze RPC. Since v0.15.24
 * it is the only source that outranks the computed draft: the sample-map xlsx
 * it used to take precedence over is gone, because it stated the plate a second
 * time and nothing kept the two statements in step.
 * Key: well coordinate (e.g. "A1"); value: mutant_id or "WT".
 */
export type WellLayout = Record<string, string>
