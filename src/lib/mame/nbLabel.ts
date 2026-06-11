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
 * Numeric sort key for a "{R}_{F}" custom barcode: "1_10" → [1, 10]. Keeps the
 * well order natural (1_2 before 1_10) instead of lexicographic string order.
 */
export function wellSortKey(customBarcode: string): [number, number] {
  const [r, f] = customBarcode.split("_");
  return [parseInt(r, 10) || 0, parseInt(f, 10) || 0];
}
