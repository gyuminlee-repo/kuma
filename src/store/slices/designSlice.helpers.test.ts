import { describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../../types/models";
import {
  addDesignResultState,
  processDesignResult,
} from "./designSlice.helpers";

function primer(mutation: string, aaPosition: number): SdmPrimerResult {
  return {
    mutation,
    aa_position: aaPosition,
    codon_pos: (aaPosition - 1) * 3,
    forward_seq: `ATGC${aaPosition}`,
    reverse_seq: `GCAT${aaPosition}`,
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    candidate_fwd_count: 1,
    candidate_rev_count: 1,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 3,
    has_offtarget: false,
    penalty: aaPosition,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "GAA",
    mt_codon: "GAT",
    overlap_seq: "ATGC",
    warnings: [],
  };
}

const wellName = (idx: number) => `A${idx + 1}`;

describe("designSlice helpers rescue capping", () => {
  it("processDesignResult never exceeds maxPrimers when rescue count is high", () => {
    const results = Array.from({ length: 7 }, (_, i) => primer(`M${i + 1}A`, i + 1));
    const processed = processDesignResult({
      result: {
        results,
        success_count: 7,
        total_count: 7,
        failed_mutations: [],
        rescue_stats: {
          pool_cascade: 0,
          auto_relax: 4,
          positions_attempted: 4,
          pool_variants_tried: 0,
        },
        rescued_mutations: results.slice(0, 4).map((r) => ({
          original: r.mutation,
          rescued_by: r.mutation,
          type: "auto_relax",
        })),
      },
      maxPrimers: 3,
      intendedMuts: new Set(results.slice(0, 3).map((r) => r.mutation)),
    });

    expect(processed.capped).toHaveLength(3);
  });

  it("addDesignResultState keeps a cascade rescue without exceeding maxPrimers", () => {
    const designResults = Array.from({ length: 5 }, (_, i) => primer(`M${i + 1}A`, i + 1));
    const rescued = primer("FAILED1A", 101);
    const next = addDesignResultState({
      mutation: rescued.mutation,
      result: rescued,
      designResults,
      failedMutations: [{ mutation: rescued.mutation, rank: 1, reason: "initial fail" }],
      rescuedMutations: [],
      wellName,
      maxPrimers: 5,
      preferredMutations: new Set(["M1A", "M2A", "M3A", "M4A", rescued.mutation]),
    });

    expect(next.designResults).toHaveLength(5);
    expect(next.designResults.map((r) => r.mutation)).toContain(rescued.mutation);
    expect(next.designResults.map((r) => r.mutation)).not.toContain("M5A");
    expect(next.successCount).toBe(5);
  });
});
