import { describe, expect, it } from "vitest";
import {
  ECHO_QUADRANTS,
  echoPlacementIssue,
  foldPersistedPlacement,
  HALF_LAYOUT_VERSION,
  predatesHalfLayout,
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

// A project saved before the half layout stored an interleaved placement, and
// every one of those values spanned the full plate width: old "A1"/"B1" were
// the odd columns 1-23 and old "A2"/"B2" the even columns 2-24. So one old
// round occupies 96 wells of each new half, and no half of it is free. Folding
// such a placement onto one half was the permissive answer, and it moved every
// source well of a reopened project without saying so.
describe("dating a stored placement by the saved app version", () => {
  it("calls a build older than the half layout old, comparing segments as numbers", () => {
    // "0.16.9" is the case a string comparison gets wrong: "0.16.9" > "0.16.59"
    // lexically, and it is an older build.
    expect(predatesHalfLayout("0.16.58")).toBe(true);
    expect(predatesHalfLayout("0.16.9")).toBe(true);
    expect(predatesHalfLayout("0.9.99")).toBe(true);
  });

  it("calls the half-layout release and anything after it current", () => {
    expect(predatesHalfLayout(HALF_LAYOUT_VERSION)).toBe(false);
    expect(predatesHalfLayout("0.16.59")).toBe(false);
    expect(predatesHalfLayout("0.16.59.1")).toBe(false);
    expect(predatesHalfLayout("0.17.0")).toBe(false);
    expect(predatesHalfLayout("1.0.0")).toBe(false);
    // The parser strips a leading "v", so a tag-shaped string is the same build.
    expect(predatesHalfLayout("v0.16.59")).toBe(false);
  });

  it("treats an unreadable or absent version as old", () => {
    // A file with no version predates the field itself. Guessing "current" here
    // is the one guess that silently moves wells.
    expect(predatesHalfLayout("")).toBe(true);
    expect(predatesHalfLayout(undefined)).toBe(true);
    expect(predatesHalfLayout(null)).toBe(true);
    expect(predatesHalfLayout("0.0.0-test")).toBe(true);
    expect(predatesHalfLayout("latest")).toBe(true);
    expect(predatesHalfLayout(16.59)).toBe(true);
  });
});

describe("reading a persisted placement", () => {
  const CURRENT = HALF_LAYOUT_VERSION;

  it("passes a placement this version wrote through unchanged", () => {
    expect(foldPersistedPlacement("A13", ["A1"], CURRENT)).toEqual({
      quadrant: "A13",
      usedQuadrants: ["A1"],
      legacySeen: [],
    });
  });

  it("normalises case and padding, and orders used halves canonically", () => {
    expect(foldPersistedPlacement(" a1 ", ["a13", "A1", "A13"], CURRENT)).toEqual({
      quadrant: "A1",
      usedQuadrants: ["A1", "A13"],
      legacySeen: [],
    });
  });

  it("drops entries the app never wrote instead of failing the load", () => {
    expect(foldPersistedPlacement("C3", ["A1", "C3", 7, null], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1"],
      legacySeen: [],
    });
  });

  it("spends both halves when any stored name is a legacy one", () => {
    // The old quadrant is not folded onto a half: its 192 wells split 96/96
    // across the two halves, so neither half is free and neither is a
    // legitimate selection.
    expect(foldPersistedPlacement("A2", [], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A13"],
      legacySeen: ["A2"],
    });
  });

  it("dates the whole placement from one legacy name, quadrant or used", () => {
    // The "A1" beside "B2" is an old name too, so it is reported rather than
    // read as the left half.
    expect(foldPersistedPlacement("B2", ["A1"], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A13"],
      legacySeen: ["B2", "A1"],
    });
    expect(foldPersistedPlacement("A13", ["B1"], CURRENT)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A13"],
      legacySeen: ["A13", "B1"],
    });
  });

  it("reads a lone A1 as old when the file is older than the half layout", () => {
    // This is the case no stored value can settle: both vocabularies spell it
    // "A1". Without the version test the old odd-column set is read as the
    // left half and the right half is declared free while primers sit in it.
    expect(foldPersistedPlacement("A1", [], "0.16.58")).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A13"],
      legacySeen: ["A1"],
    });
    expect(foldPersistedPlacement("A1", [], undefined)).toEqual({
      quadrant: null,
      usedQuadrants: ["A1", "A13"],
      legacySeen: ["A1"],
    });
    expect(foldPersistedPlacement("A1", [], "0.16.59").quadrant).toBe("A1");
  });

  it("leaves an empty placement empty however old the file is", () => {
    // A project that never picked a half states nothing about the plate, so
    // there is nothing to re-date. Reporting both halves spent here would
    // invent a plate state and make the operator clear a claim nobody made.
    expect(foldPersistedPlacement(null, [], "0.1.0")).toEqual({
      quadrant: null,
      usedQuadrants: [],
      legacySeen: [],
    });
  });
});

describe("refusing a placement the sidecar would reject", () => {
  it("passes a half that is not marked spent", () => {
    expect(echoPlacementIssue("A1", [])).toBeNull();
    expect(echoPlacementIssue("A1", ["A13"])).toBeNull();
  });

  it("refuses spent halves with no half chosen", () => {
    // This is what a legacy placement folds to, and it is the combination the
    // mapper raises on rather than quietly drawing the left half.
    expect(echoPlacementIssue(null, ["A1", "A13"])).toBe("noHalfSelected");
  });

  it("passes an empty placement, which is the untouched-plate default", () => {
    expect(echoPlacementIssue(null, [])).toBeNull();
  });

  it("refuses dispensing on top of a half the operator marked spent", () => {
    expect(echoPlacementIssue("A13", ["A13"])).toBe("halfAlreadyUsed");
  });
});
