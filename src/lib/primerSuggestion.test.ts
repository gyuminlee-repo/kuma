import { describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../types/models";
import { suggestRetryParams } from "./primerSuggestion";

function primer(tmOverlap: number): SdmPrimerResult {
  return {
    mutation: "M1A",
    aa_position: 1,
    codon_pos: 0,
    forward_seq: "ATGC",
    reverse_seq: "GCAT",
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    candidate_fwd_count: 1,
    candidate_rev_count: 1,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: tmOverlap,
    tm_condition_met: true,
    tolerance_used: 4,
    has_offtarget: false,
    penalty: 0,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "ATG",
    mt_codon: "GCG",
    overlap_seq: "ATGC",
    warnings: [],
  };
}

describe("suggestRetryParams", () => {
  it("derives overlap Tm from tm_overlap", () => {
    const suggestion = suggestRetryParams([primer(47)]);

    expect(suggestion.tmOverlap).toBe(47);
  });
});
