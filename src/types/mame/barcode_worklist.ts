/**
 * TypeScript mirror of the ``mame.export_barcode_worklist`` RPC handler.
 *
 * Keep in sync with:
 *   - kuma_core/mame/barcode_worklist.py (build_barcode_worklist, WORKLIST_HEADER)
 *   - python-core/sidecar_mame/models.py (ExportBarcodeWorklistParams)
 *   - python-core/sidecar_mame/handlers/barcode_worklist.py (response dict)
 */

import type { WtPlacement } from "./well_layout"

/** Parameters for the mame.export_barcode_worklist RPC method. */
export interface ExportBarcodeWorklistParams {
  /** The variant list, read exactly as mame.build_well_layout reads it. */
  expected_mutations_xlsx: string
  /** Destination csv. A save dialog picks it; the writer creates the folder. */
  output_path: string
  /**
   * The wells this campaign fills. Omit (or null) for the whole draft, which is
   * what a run that declares nothing uses. An empty array is refused: a
   * campaign with no wells uses no barcodes.
   */
  selected_wells?: string[] | null
  /**
   * The barcode workbook, for the seed names. Omitting it still pairs every
   * well with its {R}_{F} barcode, because that comes from the plate.
   */
  custom_barcodes_xlsx?: string | null
  /** Sheet and column holding the variant labels, for a plain variant list. */
  variant_sheet?: string | null
  variant_column?: string | null
  /**
   * Control-well policy when the source names no well, same values and same
   * default as mame.build_well_layout's. Must match what the run and the
   * preview were asked for: a worklist naming a different well than the run
   * scores sends the bench to pipette the wrong plate.
   */
  wt_placement?: WtPlacement | null
}

/** Result of a mame.export_barcode_worklist RPC call. */
export interface ExportBarcodeWorklistResult {
  /** Where the csv landed. */
  output_path: string
  /** Wells written, one row per occupied well. */
  rows: number
  /**
   * Distinct reverse (row) seed indices this campaign needs, ascending. The
   * subset of the eight an operator has to lay out, which is the question a
   * partly filled plate raises and the whole workbook cannot answer.
   */
  reverse_indices: number[]
  /** Distinct forward (column) seed indices this campaign needs, ascending. */
  forward_indices: number[]
  /**
   * Seeds a row needs that the workbook does not carry, as "F5"/"R3". Reported
   * rather than raised: a worklist naming the wells is still worth having.
   */
  missing_seeds: string[]
  /**
   * Drafted samples the selection left out, well to sample. The same statement
   * the review screen makes from the finished run, computed the same way, so a
   * sheet written before a run and a notice drawn after one cannot disagree.
   */
  excluded_occupants: Record<string, string>
}
