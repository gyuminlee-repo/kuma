/**
 * SummaryRow, the four tiles an operator reads before anything else.
 *
 * Two of them were built from different populations than their labels claim, and
 * both defects reached the bench:
 *
 * - The success rate divided a declared-selection numerator by a whole-sheet
 *   denominator, so a run declaring ten wells with every variant passing read
 *   9 %. The denominator now arrives already narrowed (see
 *   `declared_designed_ids` in the analyze handler), and what is pinned here is
 *   that this widget divides by what it is given rather than re-deriving one.
 *   `AnalyzeStepView.test.tsx` stubs `total_mutants: null`, which only ever
 *   exercised the observed-count fallback, which is why nothing caught this.
 * - The plate tile counted `wells` entries, which are verdict records, i.e. well
 *   per replicate plate. A ten-well declaration read "57 wells".
 *
 * Wording is not pinned: the prose lives in the locale files and `i18n-lint` and
 * `i18n-parity` guard the keys. What is pinned is the arithmetic that reaches
 * the DOM.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import type { RunHealthData, VerdictRecord, WellEntry } from "@/types/mame/models";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { SummaryRow } from "./SummaryRow";

function verdict(mutantId: string, patch: Partial<VerdictRecord> = {}): VerdictRecord {
  return {
    native_barcode: "barcode01",
    custom_barcode: "A01",
    file_size_kb: 100,
    read_count: 1500,
    n_mixed_positions: 0,
    max_minor_allele_fraction: 0,
    n_low_depth_positions: 0,
    consensus_n_fraction: 0,
    n_low_quality_bases: 0,
    n_input_reads: 1500,
    n_aligned_reads: 1490,
    n_mapq_failed: 0,
    n_no_call_aa: 0,
    n_span_failed: 0,
    source_path: "/data/NB01/barcode01.fastq",
    aa_sequence: "MKLVF",
    observed_nt_changes: [],
    observed_aa_changes: [],
    expected_mutations: [mutantId],
    mutant_id: mutantId,
    verdict: "PASS",
    verdict_notes: "",
    ...patch,
  };
}

function health(patch: Partial<RunHealthData> = {}): RunHealthData {
  return {
    per_plate_summary: {},
    file_size_distribution: {},
    suggested_cutoff_kb: 0,
    bimodal: false,
    suggested_method: "median_minus_2sigma",
    pore_yield_pct: null,
    throughput_timeline: null,
    barcode_distribution: null,
    cross_talk_candidates: [],
    recovered_mutants: null,
    total_mutants: null,
    recovery_rate: null,
    ...patch,
  };
}

function well(id: string, nativeBarcode: string): WellEntry {
  return {
    well: id,
    barcode: `bc-${id}-${nativeBarcode}`,
    native_barcode: nativeBarcode,
    verdict: "PASS",
    mutant_id: `R560${id}`,
    selected: nativeBarcode === "NB01",
    notes: "",
    is_fallback: false,
    fallback_reason: null,
  };
}

/** The tiles in render order: success rate, plates, readiness, status. */
function tiles(): HTMLElement[] {
  return screen.getAllByRole("status");
}

describe("SummaryRow", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      verdicts: [],
      wells: [],
      runHealth: null,
      validationErrors: [],
      isAnalyzing: false,
      analyzeDurationMs: null,
    });
  });

  it("divides a declared run by the wells it declared, not by the sheet", () => {
    // The reported run: nine R560 variants plus a WT control declared out of a
    // 96-well plate, every variant passing. The denominator the sidecar now
    // sends is the nine designed mutants on the declared plate.
    const declared = ["R560A", "R560C", "R560D", "R560E", "R560F", "R560G", "R560H", "R560I", "R560K"];
    useMameAppStore.setState({
      verdicts: [...declared.map((id) => verdict(id)), verdict("WT")],
      runHealth: health({ total_mutants: 9, recovered_mutants: 9 }),
    });

    render(<SummaryRow />);

    expect(tiles()[0]).toHaveTextContent("100%");
    expect(tiles()[0]).toHaveTextContent("9/9");
  });

  it("keeps a designed mutant that produced no verdict in the denominator", () => {
    // The other half of the rule: a well that FAILED or fell silent is still on
    // the declared plate, so it still counts against the run. Only wells the
    // operator declared absent leave the denominator, and they leave it in the
    // sidecar, not here.
    useMameAppStore.setState({
      verdicts: [verdict("R560A"), verdict("R560C")],
      runHealth: health({ total_mutants: 4 }),
    });

    render(<SummaryRow />);

    expect(tiles()[0]).toHaveTextContent("50%");
    expect(tiles()[0]).toHaveTextContent("2/4");
  });

  it("counts a well once however many replicate plates carried it", () => {
    // `wells` is one entry per verdict record, so three replicate plates of two
    // wells is six entries and two wells. Counting entries is what made a
    // ten-well declaration report "57 wells" on 96-well hardware.
    useMameAppStore.setState({
      wells: [
        well("A1", "NB01"),
        well("A1", "NB02"),
        well("A1", "NB03"),
        well("B1", "NB01"),
        well("B1", "NB02"),
        well("B1", "NB03"),
      ],
    });

    render(<SummaryRow />);

    expect(tiles()[1]).toHaveTextContent("2 wells");
    // Two wells is one plate, not six entries over 96 rounded up to one by luck.
    expect(tiles()[1]).toHaveTextContent("1");
  });

  it("does not count a record whose barcode maps to no well", () => {
    // `seq_to_well` returns "" for a barcode outside the plate, and an empty
    // string is not a well to put on the tile.
    useMameAppStore.setState({
      wells: [well("A1", "NB01"), well("", "NB01"), well("", "NB02")],
    });

    render(<SummaryRow />);

    expect(tiles()[1]).toHaveTextContent("1 wells");
  });

  it("needs more than one plate before it claims more than one", () => {
    // 97 distinct wells is where ceil(n / 96) earns its keep, and it only means
    // anything if n is distinct wells.
    const many = Array.from({ length: 97 }, (_, index) => well(`W${index}`, "NB01"));
    useMameAppStore.setState({ wells: many });

    render(<SummaryRow />);

    expect(tiles()[1]).toHaveTextContent("97 wells");
    expect(tiles()[1]).toHaveTextContent("2");
  });
});
