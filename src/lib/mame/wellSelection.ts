/**
 * Plate geometry for the well-selection grid, and nothing else.
 *
 * Mirrors `kuma_core/mame/plate_geometry.py` (`DEFAULT_ADDRESSING`): 8 rows by
 * 12 columns, filled down each column before moving right (A1, B1, ... H1, A2).
 * The order is not a preference and is not offered as one: an 8-channel pipette
 * dispenses a column at a time, so that is the order the bench fills, and the
 * `{R}_{F}` barcode is built on it.
 *
 * The sequence number here is the same 1..96 index `seq_to_well` uses, which is
 * what lets the frontend and the sidecar agree about "the i-th selected well"
 * without either of them sending an order.
 */

export const PLATE_ROW_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const
export const PLATE_ROWS = PLATE_ROW_LABELS.length
export const PLATE_COLS = 12
export const PLATE_CAPACITY = PLATE_ROWS * PLATE_COLS

/** Well label for a (0-based row, 0-based column) cell. Not zero-padded. */
export function wellAt(row: number, col: number): string {
  return `${PLATE_ROW_LABELS[row]}${col + 1}`
}

/** 1-based column-major sequence index for a (0-based row, column) cell. */
export function seqAt(row: number, col: number): number {
  return col * PLATE_ROWS + row + 1
}

/** Inverse of {@link seqAt}. */
export function cellOfSeq(seq: number): { row: number; col: number } {
  const zero = seq - 1
  return { row: zero % PLATE_ROWS, col: Math.floor(zero / PLATE_ROWS) }
}

/** Every well of the plate, in the order the bench fills it. */
export function allWellsInPlateOrder(): string[] {
  return Array.from({ length: PLATE_CAPACITY }, (_, i) => {
    const { row, col } = cellOfSeq(i + 1)
    return wellAt(row, col)
  })
}

/** The leading `count` wells: what a run with no declared selection uses. */
export function leadingWells(count: number): string[] {
  return allWellsInPlateOrder().slice(0, Math.max(0, Math.min(count, PLATE_CAPACITY)))
}

/**
 * Plate order for an arbitrary set of well labels.
 *
 * Sorting here rather than preserving click order is what makes "variant i goes
 * to the i-th selected well" mean the same thing however the operator built the
 * selection.
 */
export function sortWellsInPlateOrder(wells: Iterable<string>): string[] {
  const seen = new Set(wells)
  return allWellsInPlateOrder().filter((well) => seen.has(well))
}

/** Do two selections name the same wells? Order-insensitive. */
export function sameWells(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false
  const left = sortWellsInPlateOrder(a)
  const right = sortWellsInPlateOrder(b)
  return left.every((well, i) => well === right[i])
}
