import { act, render, screen, within } from "@testing-library/react";
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

  it("all mutations are visible without exclusion (feature removed)", () => {
    // excludedDesignMutations state removed — all design results are always included
    expect(useAppStore.getState().designResults).toHaveLength(2);
  });
});


describe("ResultTable export wells", () => {
  it("renders a well after # and updates it with canonical export sorting", () => {
    const m3 = primer("M3A", 3);
    const m1 = primer("M1A", 1);
    const m2 = primer("M2A", 2);
    const results = [m3, m1, m2];
    useAppStore.setState({
      designResults: results, failedMutations: [], successCount: 3, totalCount: 3,
      tableSorting: [], dedupInfo: {}, yPredMap: {}, customCandidates: {},
      manuallySwapped: {}, rescuedMutations: [], rescuedMutationDetails: [],
      plateMappings: [m1, m2, m3].map((r, index) => ({
        well: `${"ABC"[index]}1`, mutation: r.mutation, sequence: r.forward_seq,
        primer_name: `${r.mutation}_F`, primer_type: "forward",
      })),
    });
    render(<ResultTable />);
    const headers = screen.getAllByRole("columnheader");
    expect(headers[0]).toHaveTextContent("#");
    expect(headers[1]).toHaveTextContent("Well");
    const values = () => screen.getAllByRole("row").slice(1).map((r) => {
      const cells = within(r).getAllByRole("cell");
      return [cells[1].textContent, cells[2].textContent];
    });
    expect(values()).toEqual([["C01", "M3A"], ["A01", "M1A"], ["B01", "M2A"]]);
    act(() => useAppStore.setState({ tableSorting: [{ id: "mutation", desc: true }] }));
    expect(values()).toEqual([["A01", "M3A"], ["B01", "M2A"], ["C01", "M1A"]]);
  });

  it("keeps the empty-result state without inventing a well", () => {
    useAppStore.setState({ designResults: [], failedMutations: [], totalCount: 0, plateMappings: [] });
    render(<ResultTable />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("A01")).toBeNull();
  });
});
