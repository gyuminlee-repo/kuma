import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../../../../types/models";
import { useAppStore } from "../../../../store/appStore";
import { ExportInspector } from "../ExportInspector";

function primer(mutation: string): SdmPrimerResult {
  return {
    mutation,
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
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 3,
    has_offtarget: false,
    penalty: 1,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "GAA",
    mt_codon: "GAT",
    overlap_seq: "ATGC",
    warnings: [],
  };
}

describe("ExportInspector", () => {
  afterEach(() => {
    useAppStore.setState({
      designResults: [],
      plateMappings: [],
      evolveproCsvPath: "",
    });
  });

  it("renders empty state when no design results", () => {
    useAppStore.setState({
      designResults: [],
      plateMappings: [],
      evolveproCsvPath: "",
    });
    render(<ExportInspector />);
    expect(screen.getByText(/No design results yet/i)).toBeTruthy();
  });

  it("renders variant count and staleness when populated", () => {
    useAppStore.setState({
      designResults: [primer("M1A"), primer("R2K"), primer("L3M")],
      plateMappings: [],
      evolveproCsvPath: "/tmp/round3.csv",
    });
    render(<ExportInspector />);
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText(/linked/i)).toBeTruthy();
    expect(screen.getByText(/MAME handoff/i)).toBeTruthy();
  });

  it("variant count shows all design results", () => {
    useAppStore.setState({
      designResults: [primer("M1A"), primer("R2K"), primer("L3M")],
      plateMappings: [],
      evolveproCsvPath: "",
    });
    render(<ExportInspector />);
    expect(screen.getByText("3")).toBeTruthy();
  });
});
