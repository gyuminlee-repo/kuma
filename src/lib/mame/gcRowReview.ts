/**
 * Step 4.1 row review: what the operator may untick, and when the build must
 * not run.
 *
 * The rows and their statuses come from `mame.activity.preview_gc_rows`, which
 * runs the build's own reading stage, so nothing here judges a row. This module
 * only turns the operator's ticks into `excluded_rows`. Whether a selection
 * can be built is the build's answer too: the preview returns it as
 * `selection_refusal`, so no rule about which ticks a build needs lives here.
 */
import type {
  ExcludedGcRow,
  GcRowStatus,
  GcSourceField,
  PreviewGcRow,
} from "@/types/mame/build_evolvepro_input";

/** Rows an operator may untick. Every other status is the reader's own call. */
export const TOGGLEABLE_STATUSES: readonly GcRowStatus[] = ["used", "wt"];

/** Display order of the folded groups below the suspicious rows. */
export const ROW_GROUP_ORDER: readonly GcRowStatus[] = [
  "used",
  "wt",
  "locked",
  "set_aside",
  "ignored",
  "unjudged",
];

export function isToggleable(row: PreviewGcRow): boolean {
  return TOGGLEABLE_STATUSES.includes(row.status);
}

function samePosition(
  a: { source: GcSourceField; block_index?: number | null; row_index: number },
  b: { source: GcSourceField; block_index?: number | null; row_index: number },
): boolean {
  return a.source === b.source && (a.block_index ?? null) === (b.block_index ?? null) && a.row_index === b.row_index;
}

/** The row as the build will compare it against the file. */
export function toExcludedRow(row: PreviewGcRow): ExcludedGcRow {
  return {
    source: row.source,
    row_index: row.row_index,
    block_index: row.block_index,
    sample_name: row.sample_name,
    area: row.area,
  };
}

export function isRowExcluded(row: PreviewGcRow, excluded: readonly ExcludedGcRow[]): boolean {
  return excluded.some((entry) => samePosition(entry, row));
}

/** Tick or untick one row. Rows the operator may not untick are left alone. */
export function setRowIncluded(
  excluded: readonly ExcludedGcRow[],
  row: PreviewGcRow,
  included: boolean,
): ExcludedGcRow[] {
  const rest = excluded.filter((entry) => !samePosition(entry, row));
  if (included || !isToggleable(row)) return rest;
  return [...rest, toExcludedRow(row)];
}

/**
 * The unticked rows that still name a toggleable row of this review. An entry
 * the review no longer lists would be refused by the build as a changed file,
 * so it is not sent.
 */
export function effectiveExclusions(
  rows: readonly PreviewGcRow[],
  excluded: readonly ExcludedGcRow[],
): ExcludedGcRow[] {
  return excluded.filter((entry) =>
    rows.some((row) => isToggleable(row) && samePosition(entry, row)),
  );
}

export interface RowGroups {
  /** Kept rows the build flags (a repeated WT number, a well measured twice). */
  suspicious: PreviewGcRow[];
  /** Everything else, by status, in ROW_GROUP_ORDER. Empty groups omitted. */
  groups: { status: GcRowStatus; rows: PreviewGcRow[] }[];
}

export function groupRows(rows: readonly PreviewGcRow[]): RowGroups {
  const suspicious = rows.filter((row) => row.flags.length > 0);
  const rest = rows.filter((row) => row.flags.length === 0);
  const groups = ROW_GROUP_ORDER.flatMap((status) => {
    const members = rest.filter((row) => row.status === status);
    return members.length > 0 ? [{ status, rows: members }] : [];
  });
  return { suspicious, groups };
}
