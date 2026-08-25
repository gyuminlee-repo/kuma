import { describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../../types/models";
import {
  addDesignResultState,
  buildDesignRequestPayload,
  buildIncludedPlateState,
  getIncludedDesignResults,
  prepareDesignInput,
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

describe("designSlice helpers included result view", () => {
  it("returns all design results (always all-included after exclusion removal)", () => {
    const results = [primer("M1A", 1), primer("M2A", 2)];

    expect(getIncludedDesignResults(results)).toEqual(results);
  });

  it("builds plate state from all design results", () => {
    const sharedReverse = primer("M2A", 2);
    const results = [
      primer("M1A", 1),
      sharedReverse,
      { ...primer("M3A", 3), reverse_seq: sharedReverse.reverse_seq },
    ];

    const plateState = buildIncludedPlateState({
      designResults: results,
      wellName,
    });

    // M2A and M3A share the same reverse_seq "GCAT2", so only M2A appears as reverse representative
    expect(plateState.plateMappings.map((mapping) => mapping.mutation)).toEqual([
      "M1A",
      "M2A",
      "M3A",
      "M1A",
      "M2A",
    ]);
  });

  it("returns empty artifacts for empty design results", () => {
    const plateState = buildIncludedPlateState({
      designResults: [],
      wellName,
    });

    expect(plateState.plateMappings).toEqual([]);
    expect(plateState.dedupInfo).toEqual({});
  });
});

describe("design request rescue contract", () => {
  const payloadParams = {
    fastaPath: "/tmp/target.fasta",
    targetStart: 0,
    limitedText: "M1A",
    selectedPolymerase: "KOD",
    codonStrategy: "closest" as const,
    organism: "E. coli",
    tmFwdTarget: 62,
    tmRevTarget: 58,
    tmOverlapTarget: 42,
    gcMin: 40,
    gcMax: 60,
    primerLenEnabled: true,
    fwdLenMin: 17,
    fwdLenMax: 39,
    revLenMin: 19,
    revLenMax: 27,
    overlapMode: "partial" as const,
    rescuePool: ["M2A"],
    tolMax: 4,
    randomSeed: null,
  };

  it("disables backend rescue when auto-rescue is off", () => {
    const payload = buildDesignRequestPayload({
      ...payloadParams,
      fillOnFailure: false,
    });

    expect(payload).toMatchObject({ auto_relax: false });
    expect(payload).not.toHaveProperty("rescue_pool");
  });

  it("enables backend relax when auto-rescue is on", () => {
    const payload = buildDesignRequestPayload({
      ...payloadParams,
      fillOnFailure: true,
    });

    expect(payload).toMatchObject({ auto_relax: true });
  });

  it("uses the displayed forward range on both engine axes in full-overlap mode", () => {
    const payload = buildDesignRequestPayload({
      ...payloadParams,
      overlapMode: "full",
      fillOnFailure: true,
    });

    expect(payload).toMatchObject({
      fwd_len_min: 17,
      fwd_len_max: 39,
      rev_len_min: 17,
      rev_len_max: 39,
    });
  });
});


describe("prepareDesignInput selection set wiring", () => {
  const baseParams = {
    mutationText: "F89W\nL70V\nM1A",
    maxPrimers: 3,
    fillOnFailure: false,
    mutationInputMode: "evolvepro" as const,
    selectedGene: "",
    poolVariants: ["EXTRA1", "EXTRA2"],
  };

  it("text mode uses mutationText regardless of evolveproSelectedVariants", () => {
    const result = prepareDesignInput({
      ...baseParams,
      mutationInputMode: "text" as const,
      evolveproSelectedVariants: ["SHOULD_NOT_APPEAR"],
    });
    expect(result.limitedText).toBe("F89W\nL70V\nM1A");
  });

  it("evolvepro mode with selection set derives limitedText from selection", () => {
    const result = prepareDesignInput({
      ...baseParams,
      evolveproSelectedVariants: ["F89W", "L70V"],
      evolveproRankedCandidates: [
        { variant: "F89W", y_pred: 0.9, aa_position: 89 },
        { variant: "L70V", y_pred: 0.5, aa_position: 70 },
        { variant: "M1A", y_pred: 0.3, aa_position: 1 },
      ],
    });
    expect(result.limitedText).toBe("F89W\nL70V");
    expect(result.intendedMuts.has("F89W")).toBe(true);
    expect(result.intendedMuts.has("M1A")).toBe(false);
  });

  it("evolvepro selection respects ranked_candidates y_pred order", () => {
    const result = prepareDesignInput({
      ...baseParams,
      evolveproSelectedVariants: ["M1A", "F89W", "L70V"],  // out of rank order
      evolveproRankedCandidates: [
        { variant: "F89W", y_pred: 0.9, aa_position: 89 },
        { variant: "L70V", y_pred: 0.5, aa_position: 70 },
        { variant: "M1A", y_pred: 0.3, aa_position: 1 },
      ],
    });
    expect(result.limitedText).toBe("F89W\nL70V\nM1A");
  });

  it("evolvepro mode with empty selection produces empty limitedText", () => {
    const result = prepareDesignInput({
      ...baseParams,
      evolveproSelectedVariants: [],
      evolveproRankedCandidates: [
        { variant: "F89W", y_pred: 0.9, aa_position: 89 },
      ],
    });
    // Falls back to mutationText when selection is empty
    expect(result.limitedText).toBe("F89W\nL70V\nM1A");
  });

  it("evolvepro rescue pool excludes intended mutations from selection set", () => {
    const result = prepareDesignInput({
      ...baseParams,
      fillOnFailure: true,
      evolveproSelectedVariants: ["F89W"],
      evolveproRankedCandidates: [
        { variant: "F89W", y_pred: 0.9, aa_position: 89 },
      ],
      poolVariants: ["EXTRA1", "EXTRA2", "F89W"],
    });
    expect(result.rescuePool).not.toContain("F89W");
    expect(result.rescuePool).toContain("EXTRA1");
  });
});

describe("buildDesignRequestPayload rescue gating", () => {
  const base = {
    fastaPath: "/tmp/seq.gb",
    targetStart: 100,
    limitedText: "A1G",
    selectedPolymerase: "KOD",
    codonStrategy: "closest" as const,
    organism: "ecoli",
    tmFwdTarget: 62,
    tmRevTarget: 58,
    tmOverlapTarget: 42,
    gcMin: 40,
    gcMax: 60,
    primerLenEnabled: true,
    fwdLenMin: 18,
    fwdLenMax: 39,
    revLenMin: 19,
    revLenMax: 27,
    overlapMode: "partial" as const,
    rescuePool: ["A1V"],
    tolMax: 4,
    randomSeed: null,
  };

  it("leaves every rescue off when the fill-on-failure box is unchecked", () => {
    // The box promises that a failed mutation stays failed. The sidecar relax
    // pass used to run anyway, because auto_relax went out as a constant, and
    // it takes two nt off the length floor: a run pinned to 18 came back with
    // 17mers nobody asked for.
    const payload = buildDesignRequestPayload({ ...base, fillOnFailure: false });
    expect(payload.auto_relax).toBe(false);
    expect(payload).not.toHaveProperty("rescue_pool");
    expect(payload.fwd_len_min).toBe(18);
  });

  it("turns both rescues on when the box is checked", () => {
    const payload = buildDesignRequestPayload({ ...base, fillOnFailure: true });
    expect(payload.auto_relax).toBe(true);
    expect(payload.rescue_pool).toEqual(["A1V"]);
  });

  it("omits the length bounds when the length limit itself is off", () => {
    const payload = buildDesignRequestPayload({
      ...base,
      primerLenEnabled: false,
      fillOnFailure: false,
    });
    expect(payload).not.toHaveProperty("fwd_len_min");
  });
});
