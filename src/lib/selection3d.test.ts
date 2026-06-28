/**
 * selection3d.test.ts
 *
 * Unit tests for the pure Current-Selection 3D Analysis helpers:
 *   deriveSelectedPositions, selectedRefPositions, joinMappedYpred
 */

import { describe, it, expect } from "vitest";
import {
  deriveSelectedPositions,
  selectedRefPositions,
  joinMappedYpred,
} from "./selection3d";
import type { RankedCandidateItem } from "../types/models.generated";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mkItem = (variant: string, yPred: number, aaPosition?: number | null): RankedCandidateItem => ({
  variant,
  y_pred: yPred,
  aa_position: aaPosition ?? null,
});

// ---------------------------------------------------------------------------
// deriveSelectedPositions
// ---------------------------------------------------------------------------

describe("deriveSelectedPositions", () => {
  it("uses aa_position from ranked candidate when present", () => {
    const ranked = [mkItem("A10V", 0.9, 10)];
    const rows = deriveSelectedPositions(["A10V"], ranked, {});
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({ variant: "A10V", refPosition: 10, yPred: 0.9 });
  });

  it("falls back to regex extraction when aa_position is null", () => {
    const ranked = [mkItem("A42V", 0.7, null)];
    const rows = deriveSelectedPositions(["A42V"], ranked, {});
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({ variant: "A42V", refPosition: 42, yPred: 0.7 });
  });

  it("falls back to regex extraction when aa_position is undefined", () => {
    // Build item without aa_position field
    const item: RankedCandidateItem = { variant: "L99R", y_pred: 0.5, aa_position: undefined };
    const rows = deriveSelectedPositions(["L99R"], [item], {});
    expect(rows).toHaveLength(1);
    expect(rows[0].refPosition).toBe(99);
  });

  it("uses yPredMap when variant is not in ranked candidates", () => {
    const rows = deriveSelectedPositions(["K17E"], [], { K17E: 0.3 });
    // No ranked item, so position from regex
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({ variant: "K17E", refPosition: 17, yPred: 0.3 });
  });

  it("skips variant with no parseable position (unparseable string)", () => {
    const rows = deriveSelectedPositions(["INVALID"], [], { INVALID: 0.5 });
    expect(rows).toHaveLength(0);
  });

  it("skips variant with no y_pred source", () => {
    // Not in ranked, not in yPredMap
    const rows = deriveSelectedPositions(["A1V"], [], {});
    expect(rows).toHaveLength(0);
  });

  it("returns one row per selected variant (no dedup)", () => {
    // Two variants at the same position
    const ranked = [mkItem("A5V", 0.8, 5), mkItem("A5T", 0.6, 5)];
    const rows = deriveSelectedPositions(["A5V", "A5T"], ranked, {});
    expect(rows).toHaveLength(2);
    expect(rows[0].variant).toBe("A5V");
    expect(rows[1].variant).toBe("A5T");
  });

  it("prefers candidate y_pred over yPredMap when both exist", () => {
    const ranked = [mkItem("G20A", 0.9, 20)];
    const rows = deriveSelectedPositions(["G20A"], ranked, { G20A: 0.1 });
    expect(rows[0].yPred).toBe(0.9);
  });

  it("handles empty selectedVariants", () => {
    const rows = deriveSelectedPositions([], [mkItem("A1V", 0.5, 1)], {});
    expect(rows).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// selectedRefPositions
// ---------------------------------------------------------------------------

describe("selectedRefPositions", () => {
  it("returns sorted unique refPositions", () => {
    const ranked = [
      mkItem("A5V", 0.9, 5),
      mkItem("A3V", 0.8, 3),
      mkItem("A5T", 0.7, 5), // duplicate position
      mkItem("A1V", 0.6, 1),
    ];
    const rows = deriveSelectedPositions(["A5V", "A3V", "A5T", "A1V"], ranked, {});
    const positions = selectedRefPositions(rows);
    expect(positions).toEqual([1, 3, 5]);
  });

  it("returns empty array for empty rows", () => {
    expect(selectedRefPositions([])).toEqual([]);
  });

  it("handles single element", () => {
    const ranked = [mkItem("A7V", 0.5, 7)];
    const rows = deriveSelectedPositions(["A7V"], ranked, {});
    expect(selectedRefPositions(rows)).toEqual([7]);
  });
});

// ---------------------------------------------------------------------------
// joinMappedYpred
// ---------------------------------------------------------------------------

describe("joinMappedYpred", () => {
  it("pairs sorted remaining rows with sorted mapped positions", () => {
    const ranked = [
      mkItem("A1V", 0.9, 1),
      mkItem("A3V", 0.8, 3),
      mkItem("A5V", 0.7, 5),
    ];
    const rows = deriveSelectedPositions(["A1V", "A3V", "A5V"], ranked, {});
    // dropped: none, mapped: accession-frame positions [101, 103, 105]
    const { rows: joined, lengthMismatch } = joinMappedYpred(rows, [], [103, 101, 105]);
    expect(lengthMismatch).toBe(false);
    expect(joined).toHaveLength(3);
    // sorted by refPosition: 1->101, 3->103, 5->105
    expect(joined[0]).toMatchObject({ refPosition: 1, accPosition: 101, variant: "A1V" });
    expect(joined[1]).toMatchObject({ refPosition: 3, accPosition: 103, variant: "A3V" });
    expect(joined[2]).toMatchObject({ refPosition: 5, accPosition: 105, variant: "A5V" });
  });

  it("removes dropped positions before zip", () => {
    const ranked = [
      mkItem("A1V", 0.9, 1),
      mkItem("A3V", 0.8, 3),
      mkItem("A5V", 0.7, 5),
    ];
    const rows = deriveSelectedPositions(["A1V", "A3V", "A5V"], ranked, {});
    // refPosition 3 dropped; mapped has 2 entries for the 2 remaining
    const { rows: joined, lengthMismatch } = joinMappedYpred(rows, [3], [201, 205]);
    expect(lengthMismatch).toBe(false);
    expect(joined).toHaveLength(2);
    expect(joined[0]).toMatchObject({ refPosition: 1, accPosition: 201, variant: "A1V" });
    expect(joined[1]).toMatchObject({ refPosition: 5, accPosition: 205, variant: "A5V" });
  });

  it("truncates and signals lengthMismatch when arrays differ in length", () => {
    const ranked = [mkItem("A1V", 0.9, 1), mkItem("A3V", 0.8, 3)];
    const rows = deriveSelectedPositions(["A1V", "A3V"], ranked, {});
    // only one mapped position provided (length mismatch)
    const { rows: joined, lengthMismatch } = joinMappedYpred(rows, [], [101]);
    expect(lengthMismatch).toBe(true);
    expect(joined).toHaveLength(1);
    expect(joined[0].refPosition).toBe(1);
    expect(joined[0].accPosition).toBe(101);
  });

  it("returns empty when all positions are dropped", () => {
    const ranked = [mkItem("A1V", 0.9, 1)];
    const rows = deriveSelectedPositions(["A1V"], ranked, {});
    const { rows: joined } = joinMappedYpred(rows, [1], []);
    expect(joined).toHaveLength(0);
  });

  it("preserves order-preserving alignment for non-trivial case", () => {
    // ref positions 10, 20, 30 -> mapped to acc positions 110, 120, 130
    // input rows unsorted, mapped unsorted
    const ranked = [mkItem("A20V", 0.7, 20), mkItem("A30V", 0.6, 30), mkItem("A10V", 0.8, 10)];
    const rows = deriveSelectedPositions(["A20V", "A30V", "A10V"], ranked, {});
    const { rows: joined } = joinMappedYpred(rows, [], [130, 110, 120]);
    expect(joined[0]).toMatchObject({ refPosition: 10, accPosition: 110 });
    expect(joined[1]).toMatchObject({ refPosition: 20, accPosition: 120 });
    expect(joined[2]).toMatchObject({ refPosition: 30, accPosition: 130 });
  });
  it("two variants sharing a refPosition both receive the same accPosition (no truncation, no mismatch)", () => {
    // A5V and A5T both at refPosition 5; backend maps unique position [5] -> accPosition [205]
    const ranked = [mkItem("A5V", 0.8, 5), mkItem("A5T", 0.6, 5)];
    const rows = deriveSelectedPositions(["A5V", "A5T"], ranked, {});
    const { rows: joined, lengthMismatch } = joinMappedYpred(rows, [], [205]);
    expect(lengthMismatch).toBe(false);
    expect(joined).toHaveLength(2);
    expect(joined[0]).toMatchObject({ refPosition: 5, accPosition: 205, variant: "A5V" });
    expect(joined[1]).toMatchObject({ refPosition: 5, accPosition: 205, variant: "A5T" });
  });
});
