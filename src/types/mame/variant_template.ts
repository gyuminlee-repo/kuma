/**
 * TypeScript mirror of the ``export_variant_template`` RPC handler.
 *
 * Keep in sync with:
 *   - kuma_core/mame/io/variant_template.py (write_variant_template)
 *   - python-core/sidecar_mame/handlers/variant_template.py (response dict)
 */

/** Parameters for the export_variant_template RPC method. */
export interface ExportVariantTemplateParams {
  /** Destination xlsx. A save dialog picks it. */
  output_path: string
  /**
   * Which well carries the WT control. Omit for the last well of the plate,
   * which is where the bench puts it.
   */
  control_well?: string | null
  /** Write the control row at all. Omit for true. */
  include_control?: boolean
}

/** Result of an export_variant_template RPC call. */
export interface ExportVariantTemplateResult {
  /** Where the xlsx landed. */
  output_path: string
  /** Rows written below the header, one per well. */
  wells: number
  /** The well the control went into, or null when none was written. */
  control_well: string | null
}
