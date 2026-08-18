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

/**
 * Where the control well goes when the source names no well for it. Mirrors
 * ``kuma_core.mame.layout.WtPlacement``. Ignored for a file carrying a
 * ``Well`` column, which states the control well itself.
 *
 * ``"last_well"`` is ``DEFAULT_WT_PLACEMENT`` (H12). Only
 * ``mame.build_well_layout`` accepts this today: ``analyze`` and
 * ``validate_inputs`` build their own draft with no placement param and so
 * always take the default, regardless of what this picker is set to. This
 * setting therefore changes the preview grid, not the placement an analyze
 * run scores against.
 */
export type WtPlacement = "last_well" | "after_last_variant" | "none"

/** Parameters for the mame.build_well_layout RPC method. */
export interface BuildWellLayoutParams {
  /** Path to a KURO results xlsx containing an expected_mutations sheet. */
  expected_mutations_xlsx: string
  /** Sheet to read for a plain (non-KURO) variant list. */
  variant_sheet?: string
  /** Column to read for a plain (non-KURO) variant list. */
  variant_column?: string
  /** Control-well policy when the source names no well. Omitted = the backend default. */
  wt_placement?: WtPlacement
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
   * Draft layout rows in column-major order. The control well sits at the
   * well the source stated (a `Well` column), or otherwise where the
   * requested `wt_placement` puts it (`last_well` by default). Empty when the
   * set does not fit one plate.
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
  /**
   * The control well this draft placed, or null when this plate carries no
   * control: a file with a Well column and no wild-type row, or a row-order
   * file read with `wt_placement: "none"`. Null is a state a plate can be in,
   * not a failure to read one.
   */
  wt_well: string | null
}

/**
 * well_id -> sample_name override consumed by the analyze RPC. Since v0.15.24
 * it is the only source that outranks the computed draft: the sample-map xlsx
 * it used to take precedence over is gone, because it stated the plate a second
 * time and nothing kept the two statements in step.
 * Key: well coordinate (e.g. "A1"); value: mutant_id or "WT".
 */
export type WellLayout = Record<string, string>
