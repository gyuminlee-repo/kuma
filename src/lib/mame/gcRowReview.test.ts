import { describe, expect, it } from "vitest";
import type { PreviewGcRow } from "@/types/mame/build_evolvepro_input";
import {
  buildBlocks,
  effectiveExclusions,
  groupRows,
  isRowExcluded,
  isToggleable,
  setRowIncluded,
  toExcludedRow,
} from "./gcRowReview";

function row(overrides: Partial<PreviewGcRow>): PreviewGcRow {
  return {
    source: "round1_report_xlsx",
    block_index: 1,
    row_index: 2,
    sample_name: "5F",
    area: 100,
    kind: "variant",
    status: "used",
    reason: null,
    detail: "",
    flags: [],
    ...overrides,
  };
}

const USED = row({ row_index: 2, sample_name: "5F" });
const USED_2 = row({ row_index: 3, sample_name: "10L" });
const WT = row({ row_index: 4, sample_name: "WT", kind: "wt", status: "wt" });
const BLANK = row({ row_index: 5, sample_name: "BLANK", kind: "non_well", status: "set_aside", reason: "non_well_sample" });
const LOCKED = row({ row_index: 6, sample_name: "A1", status: "locked", reason: "other_notation", detail: "refused" });
const FLAGGED = row({ row_index: 7, sample_name: "WT", status: "wt", flags: ["duplicate_replicate"] });

describe("gcRowReview", () => {
  it("lets the operator untick only rows the build uses", () => {
    expect([USED, WT, BLANK, LOCKED, FLAGGED].map(isToggleable)).toEqual([true, true, false, false, true]);
  });

  it("ticks every row by default, matching the automatic judgement", () => {
    expect([USED, USED_2, WT].some((r) => isRowExcluded(r, []))).toBe(false);
  });

  it("records an unticked row with its sheet position and content, and ticks it back", () => {
    const off = setRowIncluded([], USED, false);
    expect(off).toEqual([{ source: "round1_report_xlsx", row_index: 2, block_index: 1, sample_name: "5F", area: 100 }]);
    expect(isRowExcluded(USED, off)).toBe(true);
    expect(isRowExcluded(USED_2, off)).toBe(false);
    expect(setRowIncluded(off, USED, true)).toEqual([]);
    expect(setRowIncluded(setRowIncluded(off, USED, false), USED, false)).toHaveLength(1);
  });

  it("refuses to untick a row the reader set aside or locked", () => {
    expect(setRowIncluded([], BLANK, false)).toEqual([]);
    expect(setRowIncluded([], LOCKED, false)).toEqual([]);
  });

  it("tells the same row number in two blocks or two files apart", () => {
    const off = [toExcludedRow(USED)];
    expect(isRowExcluded(row({ block_index: 2 }), off)).toBe(false);
    expect(isRowExcluded(row({ source: "gc_data_xlsx", block_index: null }), off)).toBe(false);
  });

  it("does not send a saved untick the review no longer lists", () => {
    const stale = { ...toExcludedRow(USED), row_index: 99 };
    expect(effectiveExclusions([USED, WT], [toExcludedRow(USED), stale])).toEqual([toExcludedRow(USED)]);
    expect(effectiveExclusions([BLANK], [toExcludedRow(BLANK)])).toEqual([]);
  });

  it("puts flagged rows first and groups the rest by status", () => {
    const { suspicious, groups } = groupRows([BLANK, USED, FLAGGED, WT, LOCKED]);
    expect(suspicious).toEqual([FLAGGED]);
    expect(groups.map((g) => g.status)).toEqual(["used", "wt", "locked", "set_aside"]);
  });

  it("blocks the build when every WT row or every measurement row of a file is unticked", () => {
    const rows = [USED, USED_2, WT, BLANK];
    expect(buildBlocks(rows, [])).toEqual([]);
    expect(buildBlocks(rows, [toExcludedRow(USED)])).toEqual([]);
    expect(buildBlocks(rows, [toExcludedRow(WT)])).toEqual([{ source: "round1_report_xlsx", reason: "allWtExcluded" }]);
    expect(buildBlocks(rows, [toExcludedRow(USED), toExcludedRow(USED_2)])).toEqual([
      { source: "round1_report_xlsx", reason: "allUsedExcluded" },
    ]);
  });

  it("does not block on WT for a file whose reader found no WT row", () => {
    const flat = row({ source: "activity_path", block_index: null });
    expect(buildBlocks([flat], [])).toEqual([]);
  });
});
