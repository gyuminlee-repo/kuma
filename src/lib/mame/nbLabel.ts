/**
 * Canonical NB label / ordering helpers for MAME widgets.
 *
 * Single source of truth for turning a native barcode (e.g. "sort_barcode06")
 * into a friendly plate label ("NB06") and for natural sort ordering. The
 * leading-zero padding is preserved by using the matched substring verbatim
 * (never int-parsing to rebuild the label).
 *
 * Cross-ref: kuma_core/mame/export/nb_label.py keeps the Python equivalents in
 * lockstep. Golden equivalence is asserted in nbLabel.test.ts /
 * tests/mame/test_nb_label.py.
 */

/**
 * Friendly plate label: "sort_barcode06" → "NB06". The matched digit run is
 * used as-is so zero padding is preserved. Names without digits (e.g.
 * "consensus") are returned unchanged.
 */
export function nbLabel(raw: string): string {
  const m = raw.match(/(\d+)/);
  return m ? `NB${m[1]}` : raw;
}

/**
 * Numeric sort key for a native barcode: "sort_barcode06" → 6. Names without
 * digits sort last (Number.MAX_SAFE_INTEGER).
 */
export function nbOrderKey(raw: string): number {
  const m = raw.match(/(\d+)/);
  return m ? parseInt(m[1], 10) : Number.MAX_SAFE_INTEGER;
}

/**
 * Column-major sort key for a "{R}_{F}" custom barcode: "1_10" → [10, 1].
 *
 * R is the reverse index (plate row 1..8) and F is the forward index (plate
 * column 1..12), so the key is [F, R]: column first, row second. That is the
 * same axis every placement rule uses, and the key is monotonic in the
 * sequence index those rules consume (seq = (F - 1) * 8 + R, see
 * kuma_core/mame/export/well_mapper.py seq_to_well and
 * excel_writer._custom_barcode_to_seq), so sorting by it reproduces the
 * seq_to_well order A1, B1, … H1, A2, …, matching the Excel NGS Results /
 * Final (matrix) / Final (legacy grid) sheets.
 *
 * Parts are compared numerically so the order stays natural (1_2 before 1_10)
 * instead of lexicographic string order.
 */
export function wellSortKey(customBarcode: string): [number, number] {
  const [r, f] = customBarcode.split("_");
  return [parseInt(f, 10) || 0, parseInt(r, 10) || 0];
}
