/**
 * Module augmentation for @tanstack/react-table.
 * Extends ColumnMeta with KURO-specific metadata fields used by ResultTable.
 */

import "@tanstack/react-table";

declare module "@tanstack/react-table" {
  // TData and TValue are required by the interface signature but not used in the
  // extension fields — the lint disable comment avoids a false-positive warning.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** Header tooltip text displayed on hover. */
    tooltip?: string;
    /** Whether clicking the cell triggers the candidate/hairpin/offtarget popover. */
    clickable?: boolean;
    /** Identifies which popover to open: "hairpin" | "offtarget" (default: candidate). */
    clickType?: string;
  }
}
