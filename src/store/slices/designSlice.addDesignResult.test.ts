/**
 * addDesignResult trims past the design count by keeping the mutations the
 * design run intended. In EVOLVEpro mode that set is the selection
 * (`prepareDesignInput(...).intendedMuts`), not the top lines of
 * `mutationText`, which is the pipeline's own seeding and ignores a hand-set
 * selection. Exercised through the real store so the source of the set is
 * what is under test.
 */

import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../appStore";
import type { SdmPrimerResult } from "../../types/models";

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

describe("addDesignResult preferred set", () => {
  afterEach(() => {
    useAppStore.getState().resetAll();
  });

  it("keeps a selected EVOLVEpro variant over a top-ranked one that was not selected", () => {
    // mutationText holds the pipeline's top three (A1V, C2V, D3V). The
    // operator deselected C2V and D3V and picked G4V and H5V instead, so the
    // design run was sent A1V, G4V, H5V. A rescue of K9V then pushes the
    // results past three and one row has to go; it must not be a selected one.
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      mutationText: "A1V\nC2V\nD3V",
      evolveproRankedCandidates: [
        { variant: "A1V", y_pred: 0.9, aa_position: 1 },
        { variant: "C2V", y_pred: 0.8, aa_position: 2 },
        { variant: "D3V", y_pred: 0.7, aa_position: 3 },
        { variant: "G4V", y_pred: 0.6, aa_position: 4 },
        { variant: "H5V", y_pred: 0.5, aa_position: 5 },
      ],
      evolveproSelectedVariants: ["A1V", "G4V", "H5V"],
      evolveproSelectionManual: true,
      maxPrimers: 3,
      // D3V is a row left over from before the selection changed; it is the
      // one that is neither selected nor the rescue.
      designResults: [primer("A1V", 1), primer("G4V", 4), primer("D3V", 3)],
    });

    useAppStore.getState().addDesignResult("K9V", primer("K9V", 9));

    const kept = useAppStore.getState().designResults.map((r) => r.mutation);
    expect(kept).toHaveLength(3);
    expect(kept).toContain("K9V");
    expect(kept).toContain("G4V");
    expect(kept).not.toContain("D3V");
  });

  it("still reads mutationText outside EVOLVEpro mode", () => {
    useAppStore.setState({
      mutationInputMode: "text",
      mutationText: "A1V\nG4V",
      evolveproSelectedVariants: [],
      maxPrimers: 2,
      designResults: [primer("A1V", 1), primer("D3V", 3)],
    });

    useAppStore.getState().addDesignResult("G4V", primer("G4V", 4));

    const kept = useAppStore.getState().designResults.map((r) => r.mutation);
    expect(kept).toEqual(expect.arrayContaining(["A1V", "G4V"]));
    expect(kept).not.toContain("D3V");
  });
});
