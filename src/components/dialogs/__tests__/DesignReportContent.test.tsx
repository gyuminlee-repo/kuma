import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SdmPrimerResult } from "../../../types/models";
import { useAppStore } from "../../../store/appStore";
import { EMPTY_RESCUE_STATS } from "../../../store/slices/designSlice.helpers";
import { DesignReportContent } from "../DesignReportContent";

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

function seedReportState() {
  useAppStore.setState({
    designResults: [primer("M1A", 1), primer("R2K", 2)],
    failedMutations: [],
    totalCount: 2,
    rescueStats: EMPTY_RESCUE_STATS,
    rescuedMutationDetails: [],
  });
}

describe("DesignReportContent (standalone, no Dialog wrapper)", () => {
  afterEach(() => {
    // Reset to avoid leakage across tests
    useAppStore.setState({
      designResults: [],
      failedMutations: [],
      totalCount: 0,
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });
  });

  it("renders the KPI table (Succeeded stat) when mounted without a Dialog", () => {
    seedReportState();
    render(<DesignReportContent />);
    // "Design Report" title from en.json
    expect(screen.getByText("Design Report")).toBeTruthy();
    // The Primer Design "Succeeded" row shows "2/2"
    expect(screen.getAllByText("2/2").length).toBeGreaterThan(0);
  });

  it("omits the close button when onClose is not provided (Inspector context)", () => {
    seedReportState();
    render(<DesignReportContent />);
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("renders a close button that calls onClose when provided", async () => {
    seedReportState();
    const onClose = vi.fn();
    render(<DesignReportContent onClose={onClose} />);
    const closeBtn = screen.getByRole("button", { name: "Close" });
    expect(closeBtn).toBeTruthy();
    closeBtn.click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("returns null when designResults is empty", () => {
    useAppStore.setState({ designResults: [], failedMutations: [], totalCount: 0 });
    const { container } = render(<DesignReportContent />);
    expect(container.firstChild).toBeNull();
  });
});
