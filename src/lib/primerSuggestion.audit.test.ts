import { describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../types/models";
import { suggestRetryParams } from "./primerSuggestion";

function primer(overrides: Partial<SdmPrimerResult> = {}): SdmPrimerResult {
  return {
    mutation: "A2V", aa_position: 2, codon_pos: 3,
    forward_seq: "ATGC", reverse_seq: "GCAT", fwd_len: 20, rev_len: 20,
    overlap_len: 18, candidate_fwd_count: 1, candidate_rev_count: 1,
    tm_no_fwd: 62, tm_no_rev: 58, tm_overlap: 42,
    tm_condition_met: true, tolerance_used: 4, has_offtarget: false,
    penalty: 0, gc_fwd: 50, gc_rev: 50, wt_codon: "GCT", mt_codon: "GTT",
    overlap_seq: "ATGC", warnings: [], ...overrides,
  };
}

const defaults = {
  tmFwd: 61, tmRev: 57, tmOverlap: 41, gcMin: 35, gcMax: 65,
  fwdLenMin: 20, fwdLenMax: 35, revLenMin: 19, revLenMax: 30,
};

describe("retry suggestions with missing thermodynamic measurements", () => {
  it("falls back per axis when every measurement on that axis is non-finite", () => {
    const result = suggestRetryParams([
      primer({ tm_no_fwd: NaN, tm_no_rev: Infinity, tm_overlap: -Infinity }),
      primer({ tm_no_fwd: NaN, tm_no_rev: NaN, tm_overlap: NaN }),
    ], defaults);
    expect(result.tmFwd).toBe(61);
    expect(result.tmRev).toBe(57);
    expect(result.tmOverlap).toBe(41);
    expect(Object.values(result).every(Number.isFinite)).toBe(true);
  });

  it("does not replace finite zero or valid evidence on the other axes", () => {
    const result = suggestRetryParams([
      primer({ tm_no_fwd: NaN, tm_no_rev: 0, tm_overlap: 46 }),
    ], defaults);
    expect(result.tmFwd).toBe(61);
    expect(result.tmRev).toBe(0);
    expect(result.tmOverlap).toBe(46);
  });

  it("keeps the finite median when only some measurements are missing", () => {
    const result = suggestRetryParams([
      primer({ tm_no_fwd: NaN }), primer({ tm_no_fwd: 60 }), primer({ tm_no_fwd: 64 }),
    ], defaults);
    expect(result.tmFwd).toBe(62);
  });
});
