import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../../../../types/models";
import { useAppStore } from "../../../../store/appStore";
import { ParameterInspector } from "../ParameterInspector";

function primer(mutation: string, warnings: string[] = []): SdmPrimerResult {
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
    warnings,
  };
}

describe("ParameterInspector", () => {
  afterEach(() => {
    useAppStore.setState({
      designResults: [],
      plateMappings: [],
      parsedMutations: [],
    });
  });

  it("renders placeholders when no design has run", () => {
    useAppStore.setState({
      designResults: [],
      plateMappings: [],
      parsedMutations: [],
    });
    render(<ParameterInspector />);
    expect(screen.getByText(/Parameter Inspector/i)).toBeTruthy();
    expect(screen.getAllByText("--").length).toBeGreaterThanOrEqual(3);
  });

  it("renders metrics when designResults and parsedMutations populated", () => {
    useAppStore.setState({
      designResults: [primer("M1A"), primer("R2K", ["lowTm"])],
      plateMappings: [],
      parsedMutations: [
        { mutation: "M1A", aa_position: 1, wt_aa: "M", mt_aa: "A" },
        { mutation: "R2K", aa_position: 2, wt_aa: "R", mt_aa: "K" },
      ] as never,
    });
    render(<ParameterInspector />);
    expect(screen.getByText("2")).toBeTruthy(); // primers
    expect(screen.getByText("1")).toBeTruthy(); // warnings
  });
});
