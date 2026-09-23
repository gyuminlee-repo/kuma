import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { SdmPrimerResult } from "@/types/models";
import { makeResultTableColumns } from "./resultTableColumns";

function row(overrides: Partial<SdmPrimerResult> = {}): SdmPrimerResult {
  return {
    mutation: "A1V", aa_position: 1, codon_pos: 0, forward_seq: "ATGC", reverse_seq: "GCAT",
    fwd_len: 20, rev_len: 20, overlap_len: 18, candidate_fwd_count: 1, candidate_rev_count: 1,
    candidate_count: 1, tm_no_fwd: 62, tm_no_rev: 58, tm_overlap: 42, tm_condition_met: true,
    tolerance_used: 1, has_offtarget: false, penalty: 0, gc_fwd: 50, gc_rev: 50,
    wt_codon: "GCT", mt_codon: "GTT", overlap_seq: "ATGC", warnings: [],
    ...overrides,
  };
}

describe("synthesis score column", () => {
  it("renders a missing backend score as unavailable rather than a perfect 100", () => {
    const columns = makeResultTableColumns({
      groupColorMap: new Map(), overlapMode: "partial", swapped: {},
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

describe("hairpin column", () => {
  function hairpinCell() {
    const columns = makeResultTableColumns({
      groupColorMap: new Map(), overlapMode: "partial", swapped: {},
      customCandidates: {}, rescuedMutations: new Set(), rescueDetailMap: new Map(),
      removeDesignResult: vi.fn(), yPredMap: {}, t: ((key: string) => key) as never,
    });
    const hairpin = columns.find((column) => column.id === "hairpin");
    if (!hairpin?.cell) throw new Error("Hairpin column missing");
    return hairpin.cell as (info: { row: { original: SdmPrimerResult } }) => ReactNode;
  }

  it("tints amber only when an engine warn flag is set", () => {
    const cell = hairpinCell();
    render(
      <>
        {cell({
          row: {
            original: row({
              hairpin_tm_fwd: 55,
              hairpin_warn_fwd: true,
              homodimer_warn_rev: false,
            }),
          },
        })}
      </>,
    );
    const badge = screen.getByText("55");
    expect(badge.className).toContain("text-warning");
  });

  it("does not infer the warning from the raw Tm anymore", () => {
    const cell = hairpinCell();
    // Tm 55 used to be amber by the hardcoded `worst > 40`; with the engine
    // verdict false (folded fraction below the limit at this pair's Ta) it
    // renders neutral.
    render(
      <>
        {cell({
          row: {
            original: row({
              hairpin_tm_fwd: 55,
              hairpin_warn_fwd: false,
              hairpin_warn_rev: false,
              homodimer_warn_fwd: false,
              homodimer_warn_rev: false,
            }),
          },
        })}
      </>,
    );
    const badge = screen.getByText("55");
    expect(badge.className).not.toContain("text-warning");
  });

  it("falls back to the legacy Tm threshold when all warn flags are absent", () => {
    const cell = hairpinCell();
    // Rows serialized before the flags existed, or rows whose pair Ta is
    // unknown after a swap, carry none of the four warn flags. The
    // frontend cannot recompute the engine's theta (no dH available), so
    // it falls back to the pre-engine legacy threshold rather than
    // silently rendering these rows as warning-free.
    render(<>{cell({ row: { original: row({ hairpin_tm_fwd: 55 }) } })}</>);
    const badge = screen.getByText("55");
    expect(badge.className).toContain("text-warning");
  });

  it("does not warn via the legacy fallback below the legacy threshold", () => {
    const cell = hairpinCell();
    // Same no-flags case, but the worst Tm (30) is below the legacy 40
    // threshold, so no warning is shown.
    render(<>{cell({ row: { original: row({ hairpin_tm_fwd: 30 }) } })}</>);
    const badge = screen.getByText("30");
    expect(badge.className).not.toContain("text-warning");
  });

  it("falls back per-structure when only the hairpin flags are absent (reverse propagation)", () => {
    const cell = hairpinCell();
    // applyReversePropagation clears only hairpin_warn_fwd/rev to undefined
    // (Ta-dependent, cannot be reused after re-pairing); it copies
    // homodimer_warn_fwd/rev through unchanged. A row-level "any flag
    // present -> trust the engine" check treats this row as fully judged
    // and reads the absent hairpin flags as false, hiding a real hairpin
    // warning. The fallback must be evaluated per structure.
    render(
      <>
        {cell({
          row: {
            original: row({
              hairpin_tm_fwd: 55,
              hairpin_warn_fwd: undefined,
              hairpin_warn_rev: undefined,
              homodimer_warn_fwd: false,
              homodimer_warn_rev: false,
              homodimer_tm_fwd: 30,
              homodimer_tm_rev: 30,
            }),
          },
        })}
      </>,
    );
    const badge = screen.getByText("55");
    expect(badge.className).toContain("text-warning");
  });

  it("renders the neutral placeholder when no structure was found", () => {
    const cell = hairpinCell();
    render(<>{cell({ row: { original: row() } })}</>);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
