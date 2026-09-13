import { describe, expect, it } from "vitest";
import {
  ECHO_QUADRANTS,
  foldLegacyQuadrant,
  foldLegacyQuadrants,
  isColumnInHalf,
  isForwardRow,
  otherHalves,
  quadrantFirstColumn,
  quadrantLastColumn,
  quadrantsFilledAfterRun,
} from "./echoQuadrant";

describe("Echo source plate halves", () => {
  it("offers exactly the two halves the core does", () => {
    // kuma_core/kuro/plate_quadrant.QUADRANTS. A third entry here would put an
    // option in the picker the sidecar rejects.
    expect([...ECHO_QUADRANTS]).toEqual(["A1", "A13"]);
  });

  it("puts the halves on contiguous, non-overlapping column blocks", () => {
    expect([quadrantFirstColumn("A1"), quadrantLastColumn("A1")]).toEqual([1, 12]);
    expect([quadrantFirstColumn("A13"), quadrantLastColumn("A13")]).toEqual([13, 24]);
  });

  it("tests membership by column range, not by column parity", () => {
    // The interleaved layout this replaced called every second column of a
    // half someone else's. These four assertions are exactly where the two
    // rules disagree.
    expect(isColumnInHalf(1, "A1")).toBe(true);
    expect(isColumnInHalf(2, "A1")).toBe(true);
    expect(isColumnInHalf(13, "A1")).toBe(false);
    expect(isColumnInHalf(14, "A13")).toBe(true);
  });

  it("names the one other half", () => {
    expect(otherHalves("A1")).toEqual(["A13"]);
    expect(otherHalves("A13")).toEqual(["A1"]);
  });

  it("counts a run as spending one half, and a stated one only once", () => {
    expect(quadrantsFilledAfterRun("A1", [])).toBe(1);
    expect(quadrantsFilledAfterRun("A1", ["A1"])).toBe(1);
    expect(quadrantsFilledAfterRun("A1", ["A13"])).toBe(2);
  });

  it("reads direction off row parity alone", () => {
    // Forward at 384 row 2r, reverse at 2r+1, in either half.
    expect(isForwardRow(0)).toBe(true);
    expect(isForwardRow(1)).toBe(false);
    expect(isForwardRow(14)).toBe(true);
    expect(isForwardRow(15)).toBe(false);
  });
});

// A project saved before the half layout stores one of four interleaved names.
// The load paths fold rather than test membership, because a hardcoded list
// drops whatever is not on it: the old list held neither "A13" nor anything a
// future rename adds, so a project saved today and reopened tomorrow lost its
// placement without a message.
describe("folding a persisted quadrant onto a half", () => {
  it("folds each legacy name onto the half it covered", () => {
    expect(foldLegacyQuadrant("A1")).toBe("A1");
    expect(foldLegacyQuadrant("B1")).toBe("A1");
    expect(foldLegacyQuadrant("A2")).toBe("A13");
    expect(foldLegacyQuadrant("B2")).toBe("A13");
  });

  it("keeps a value already written as a half", () => {
    expect(foldLegacyQuadrant("A13")).toBe("A13");
  });

  it("refuses anything the app never wrote", () => {
    expect(foldLegacyQuadrant("C3")).toBeNull();
    expect(foldLegacyQuadrant("")).toBeNull();
    expect(foldLegacyQuadrant(undefined)).toBeNull();
    expect(foldLegacyQuadrant(null)).toBeNull();
    expect(foldLegacyQuadrant(1)).toBeNull();
  });

  it("de-duplicates a list where two legacy names were one half", () => {
    // A1 and B1 were the forward and reverse sets of the same columns, so a
    // plate with both spent has one half spent, not two.
    expect(foldLegacyQuadrants(["A1", "B1"])).toEqual(["A1"]);
    expect(foldLegacyQuadrants(["A2", "B2"])).toEqual(["A13"]);
    expect(foldLegacyQuadrants(["A1", "B1", "A2", "B2"])).toEqual(["A1", "A13"]);
  });

  it("drops unknown entries from a list instead of failing the load", () => {
    expect(foldLegacyQuadrants(["A1", "C3", 7, null])).toEqual(["A1"]);
    expect(foldLegacyQuadrants([])).toEqual([]);
  });
});
