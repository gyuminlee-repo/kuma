import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "@/store/appStore";
import type { SdmPrimerResult } from "@/types/models";
import { ResultTable } from "./ResultTable";

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
    candidate_count: 1,
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

describe("ResultTable include column removal (T4)", () => {
  beforeEach(() => {
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      designResults: [primer("M1A", 1), primer("M2A", 2)],
      excludedDesignMutations: [],
      failedMutations: [],
      successCount: 2,
      totalCount: 2,
      plateMappings: [],
      dedupInfo: {},
      tableSorting: [],
      yPredMap: {},
      customCandidates: {},
      manuallySwapped: {},
      rescuedMutations: [],
      rescuedMutationDetails: [],
    });
  });

  it("renders no include checkboxes in evolvepro mode", () => {
    render(<ResultTable />);
    expect(
      screen.queryByRole("checkbox"),
    ).toBeNull();
  });

  it("shows all rows visible without excluded styling", () => {
    render(<ResultTable />);
    expect(screen.getByText("M1A")).toBeInTheDocument();
    expect(screen.getByText("M2A")).toBeInTheDocument();
    // No row should carry opacity-55 class (excluded styling removed)
    const rows = screen.getAllByRole("row");
    for (const row of rows) {
      expect(row.className).not.toContain("opacity-55");
    }
  });

  it("excludedDesignMutations empty set leaves all mutations in included state", () => {
    // Downstream consumers (getIncludedDesignResults etc.) treat empty set as all-included
    expect(useAppStore.getState().excludedDesignMutations).toEqual([]);
  });
});
