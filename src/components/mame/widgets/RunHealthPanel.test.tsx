import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunHealthBreakdown, RunHealthData } from "@/types/mame/models";
import { RunHealthPanel } from "./RunHealthPanel";

function breakdown(overrides: Partial<RunHealthBreakdown> = {}): RunHealthBreakdown {
  return {
    pass: 0,
    ambiguous: 0,
    mixed: 0,
    frameshift: 0,
    many: 0,
    lowdepth: 0,
    no_call: 0,
    wrong_aa: 0,
    fail: 0,
    fallback: 0,
    total: 0,
    ...overrides,
  };
}

function makeHealth(overrides: Partial<RunHealthData> = {}): RunHealthData {
  return {
    per_plate_summary: {
      // WT-PASS plate: every well passes → D = 2/2.
      sort_barcode01: breakdown({ pass: 2, total: 2 }),
      // Mixed plate: D = pass + ambiguous = 1 + 1 = 2/3.
      sort_barcode02: breakdown({ pass: 1, ambiguous: 1, mixed: 1, fail: 1, total: 3 }),
    },
    file_size_distribution: {},
    suggested_cutoff_kb: 50,
    bimodal: false,
    suggested_method: "p05",
    pore_yield_pct: null,
    throughput_timeline: null,
    barcode_distribution: null,
    cross_talk_candidates: [],
    recovered_mutants: 3,
    total_mutants: 4,
    recovery_rate: 0.75,
    ...overrides,
  };
}

describe("RunHealthPanel — recovery / detected / class table", () => {
  // AC8: recovery header shows "R/T (Z%)" when data is available.
  it("renders the recovery header with R/T (Z%)", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    const header = screen.getByTestId("run-health-recovery");
    expect(header).toHaveTextContent("Recovery");
    expect(header).toHaveTextContent("3/4 (75%)");
  });

  // AC8: recovery header shows n/a (never "0%") when fields are null.
  it("renders n/a in the recovery header when recovery is unavailable", () => {
    const health = makeHealth({
      recovered_mutants: null,
      total_mutants: null,
      recovery_rate: null,
    });
    render(<RunHealthPanel health={health} sections={["verdict-breakdown"]} />);
    const header = screen.getByTestId("run-health-recovery");
    expect(header).toHaveTextContent("n/a");
    expect(header).not.toHaveTextContent("0%");
  });

  // Per-plate "Detected D/T" line removed; bars now carry actual per-segment counts.
  it("shows per-segment counts on bars and drops the per-plate detected line", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    expect(screen.queryByText(/Detected \d+\/\d+/)).toBeNull();
    const counts = screen.getAllByTestId("seg-count").map((e) => e.textContent);
    // sort_barcode01 pass=2 → "2"; sort_barcode02 pass/amb/mixed = 1/1/1 → three "1".
    expect(counts).toContain("2");
    expect(counts.filter((c) => c === "1").length).toBe(3);
  });

  // AC10: class-count table equals the run-level sums across perPlate.
  it("renders a class-count table summing every plate", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    const table = screen.getByTestId("run-health-class-counts");

    // pass: 2 + 1 = 3
    const passRow = within(table).getByText("Pass").closest("tr");
    expect(passRow).not.toBeNull();
    expect(within(passRow as HTMLElement).getByText("3")).toBeInTheDocument();

    // ambiguous: 0 + 1 = 1
    const ambiguousRow = within(table).getByText("Ambiguous").closest("tr");
    expect(ambiguousRow).not.toBeNull();
    expect(within(ambiguousRow as HTMLElement).getByText("1")).toBeInTheDocument();

    // mixed: 0 + 1 = 1
    const mixedRow = within(table).getByText("Mixed").closest("tr");
    expect(mixedRow).not.toBeNull();
    expect(within(mixedRow as HTMLElement).getByText("1")).toBeInTheDocument();

    // no_call: 0 across both plates
    const noCallRow = within(table).getByText("No call").closest("tr");
    expect(noCallRow).not.toBeNull();
    expect(within(noCallRow as HTMLElement).getByText("0")).toBeInTheDocument();
  });
});
