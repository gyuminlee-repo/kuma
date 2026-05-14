import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../../../../types/models";
import { useAppStore } from "../../../../store/appStore";
import { EMPTY_RESCUE_STATS } from "../../../../store/slices/designSlice.helpers";
import { DesignReportInspector } from "../DesignReportInspector";

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

describe("DesignReportInspector", () => {
  afterEach(() => {
    useAppStore.setState({
      designResults: [],
      failedMutations: [],
      totalCount: 0,
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });
  });

  it("renders empty state when designResults is empty", () => {
    useAppStore.setState({ designResults: [], failedMutations: [], totalCount: 0 });
    render(<DesignReportInspector />);
    // en.json: "Run Design first — the report will appear here"
    expect(screen.getByText(/Run Design first/i)).toBeTruthy();
  });

  it("renders DesignReportContent (KPI heading) when designResults is non-empty", () => {
    useAppStore.setState({
      designResults: [primer("M1A", 1), primer("R2K", 2)],
      failedMutations: [],
      totalCount: 2,
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });
    render(<DesignReportInspector />);
    expect(screen.getByText("Design Report")).toBeTruthy();
    expect(screen.getAllByText("2/2").length).toBeGreaterThan(0);
  });
});
