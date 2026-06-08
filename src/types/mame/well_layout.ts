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
   * Draft layout rows in column-major order (WT control last when it fits the
   * 96-well plate). Editable by the user before being passed back to analyze.
   */
  draft: WellLayoutRow[]
  /** Number of draft rows (mutant wells + optional WT well). */
  count: number
}

/**
 * well_id -> sample_name override consumed by the analyze RPC as the
 * highest-priority well->sample source (takes precedence over sample_map_xlsx).
 * Key: well coordinate (e.g. "A1"); value: mutant_id or "WT".
 */
export type WellLayout = Record<string, string>
