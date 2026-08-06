import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import { VERDICT_LABEL } from "@/lib/mame/verdictColors";
import type { RunHealthBreakdown, RunHealthData, VerdictClass } from "@/types/mame/models";
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

const ALL_CLASSES: VerdictClass[] = [
  "PASS",
  "AMBIGUOUS",
  "MIXED",
  "WRONG_AA",
  "FRAMESHIFT",
  "MANY",
  "LOWDEPTH",
  "NO_CALL",
];

/**
 * The eight explanations, read from the locale source instead of retyped here,
 * so a reworded sentence needs no test edit and a surface wired to the wrong
 * VERDICT_HELP_KEY entry still fails (the expectation does not come from that
 * same map).
 */
const HELP = en.mame.verdictBadge.help;

/** Nearest self-or-ancestor matching `sel`; throws rather than returning null. */
function closestOrThrow(node: HTMLElement, sel: string): HTMLElement {
  const found = node.closest(sel);
  if (!found) throw new Error(`no ${sel} at or above "${node.textContent}"`);
  return found as HTMLElement;
}

describe("RunHealthPanel, recovery / detected / class table", () => {
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

  // Per-plate headline shows strict pass-rate (pass / total), AMBIGUOUS excluded.
  it("renders per-plate strict pass-rate headlines", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    // WT-PASS plate: 2 pass / 2 total = 100%.
    expect(screen.getByText("100%")).toBeInTheDocument();
    // Mixed plate: 1 pass / 3 total = 33% (ambiguous not counted as pass).
    expect(screen.getByText("33%")).toBeInTheDocument();
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

  // (D) Both places the verdict legend appears in this panel explain themselves
  // on hover. jsdom renders no native tooltip, so the hover itself cannot be
  // observed: these assert the `title` attribute a browser turns into one.
  // Attribute contracts, not rendering tests.
  it("gives every chart-legend item its explanation as a hover title", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    const legend = screen.getByRole("list", { name: en.mame.runHealth.legendAriaLabel });
    for (const cls of ALL_CLASSES) {
      const item = closestOrThrow(within(legend).getByText(VERDICT_LABEL[cls]), '[role="listitem"]');
      expect(item).toHaveAttribute("title", HELP[cls]);
    }
  });

  it("gives every class-count row header the same explanation, without visible text", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    const table = screen.getByTestId("run-health-class-counts");
    for (const cls of ALL_CLASSES) {
      const header = closestOrThrow(within(table).getByText(VERDICT_LABEL[cls]), "th");
      expect(header).toHaveAttribute("title", HELP[cls]);
      // The sentence must stay in the attribute. Rendering it as text would
      // break the exact-text lookups the class-count test above depends on.
      expect(header).not.toHaveTextContent(HELP[cls]);
    }
  });

  // #5: when embedded under a titled DataPanel, the per-section heading is
  // visually hidden (sr-only) to avoid a duplicated title, but kept for a11y.
  it("hides the section heading visually (sr-only) when showSectionHeadings=false", () => {
    const { rerender } = render(
      <RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />,
    );
    expect(
      screen.getByRole("heading", { name: "Verdict breakdown" }).className,
    ).not.toContain("sr-only");
    rerender(
      <RunHealthPanel
        health={makeHealth()}
        sections={["verdict-breakdown"]}
        showSectionHeadings={false}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Verdict breakdown" }).className,
    ).toContain("sr-only");
  });
});
