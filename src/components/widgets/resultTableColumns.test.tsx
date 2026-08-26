import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { SdmPrimerResult } from "@/types/models";
import { makeResultTableColumns } from "./resultTableColumns";

function row(): SdmPrimerResult {
  return {
    mutation: "A1V", aa_position: 1, codon_pos: 0, forward_seq: "ATGC", reverse_seq: "GCAT",
    fwd_len: 20, rev_len: 20, overlap_len: 18, candidate_fwd_count: 1, candidate_rev_count: 1,
    candidate_count: 1, tm_no_fwd: 62, tm_no_rev: 58, tm_overlap: 42, tm_condition_met: true,
    tolerance_used: 1, has_offtarget: false, penalty: 0, gc_fwd: 50, gc_rev: 50,
    wt_codon: "GCT", mt_codon: "GTT", overlap_seq: "ATGC", warnings: [],
  };
}

describe("synthesis score column", () => {
  it("renders a missing backend score as unavailable rather than a perfect 100", () => {
    const columns = makeResultTableColumns({
      groupColorMap: new Map(), codonStrategy: "closest", overlapMode: "partial", swapped: {},
      customCandidates: {}, rescuedMutations: new Set(), rescueDetailMap: new Map(),
      removeDesignResult: vi.fn(), yPredMap: {}, t: ((key: string) => key) as never,
    });
    const synth = columns.find((column) => column.id === "synth");
    if (!synth?.cell) throw new Error("Synthesis column missing");
    const cell = synth.cell as (info: { row: { original: SdmPrimerResult } }) => ReactNode;
    render(<>{cell({ row: { original: row() } })}</>);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("100")).not.toBeInTheDocument();
  });
});
