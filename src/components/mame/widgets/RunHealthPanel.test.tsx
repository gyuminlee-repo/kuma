import { render, screen, within } from "@testing-library/react";
import { useTranslation } from "react-i18next";
import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import { VERDICT_LABEL } from "@/lib/mame/verdictColors";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { RunHealthBreakdown, RunHealthData, VerdictClass } from "@/types/mame/models";
import { RUN_HEALTH_QC_SECTIONS, RunHealthPanel } from "./RunHealthPanel";

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

/**
 * Records the identity of the two mutant-recovery-bar dependencies this file
 * cannot control directly, so the recovery test below can assert its own
 * premise instead of assuming it. Rendered as a sibling of the panel: `t` and
 * the store selection behave the same wherever they are read.
 */
function DepIdentityProbe({ sink }: { sink: { t: unknown[]; replicates: unknown[] } }) {
  const { t } = useTranslation();
  const replicates = useMameAppStore((state) => state.replicates);
  sink.t.push(t);
  sink.replicates.push(replicates);
  return null;
}

describe("RunHealthPanel, recovery / detected / class table", () => {
  // The recovery-rate header is withdrawn: SummaryRow already reports a success
  // rate over the same designed set, and that one counts PASS alone, which is what
  // the pick list ships. Two headline percentages differing only in whether
  // AMBIGUOUS counts let a reader quote the higher one.
  it("does not render a recovery-rate header", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);
    expect(screen.queryByTestId("run-health-recovery")).toBeNull();
    expect(screen.queryByText("3/4 (75%)")).toBeNull();
  });

  // The bar below it still reads the designed-set scalars, so a null recovery must
  // not crash the section or print a bogus 0%.
  it("renders the section without a rate when recovery fields are null", () => {
    const health = makeHealth({
      recovered_mutants: null,
      total_mutants: null,
      recovery_rate: null,
    });
    render(<RunHealthPanel health={health} sections={["verdict-breakdown"]} />);
    expect(screen.queryByTestId("run-health-recovery")).toBeNull();
    expect(screen.queryByText("0%")).toBeNull();
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

  /**
   * The mutant-recovery bar is memoised. Before `recoveredMutants` joined its
   * dependency list, a re-analysis that moved only the recovered count left the
   * bar (and its "not recovered" legend) on the previous run while the recovery
   * header above it already showed the new one, which is exactly the
   * contradiction the comment above that memo promises cannot happen.
   *
   * The fixture is built so the memo has one changed input and no others:
   *  - total_mutants stays 4. Moving it too would recompute through a
   *    dependency that was already listed, and the test would pass either way.
   *    Holding it fixed is also the realistic case: total_mutants is derived
   *    from the expected-mutations workbook, and changing that workbook clears
   *    the results instead of re-rendering with them.
   *  - the store is never written, so `replicates` keeps its identity, and `t`
   *    is stable across a rerender.
   * The last two are asserted from the probe rather than assumed, so a store or
   * i18n change that breaks the premise fails here loudly instead of quietly
   * turning this into a test that cannot fail.
   */
  it("moves the not-recovered figure when only the recovered count changed", () => {
    const sink = { t: [] as unknown[], replicates: [] as unknown[] };
    const tree = (recovered: number) => (
      <>
        <DepIdentityProbe sink={sink} />
        <RunHealthPanel
          health={makeHealth({
            recovered_mutants: recovered,
            recovery_rate: recovered / 4,
          })}
          sections={["verdict-breakdown"]}
        />
      </>
    );

    const { rerender } = render(tree(3));
    // 4 designed - 3 recovered. The bar is now the only reader of recovered_mutants
    // in this section, so it alone has to move when that scalar moves.
    expect(screen.getByText("Not recovered: 1")).toBeInTheDocument();

    rerender(tree(2));

    // Premise: every other input to the memo held its identity across the
    // rerender, so a moved figure can only come from the added dependency.
    expect(sink.t.length).toBeGreaterThan(1);
    expect(new Set(sink.t).size).toBe(1);
    expect(new Set(sink.replicates).size).toBe(1);

    expect(screen.getByText("Not recovered: 2")).toBeInTheDocument();
    expect(screen.queryByText("Not recovered: 1")).not.toBeInTheDocument();
  });
});

/**
 * A subset that asks for a MinKNOW-only section on a run with no raw data used
 * to draw an empty panel: the whole `hasMinKnow` block is skipped, no exception
 * is raised, and the one line explaining the absence was gated on
 * `sections === undefined`. Those four sections are the entire raw-run surface,
 * so silence there is indistinguishable from a run that went well.
 */
describe("RunHealthPanel, absent MinKNOW data under a section subset", () => {
  it("states the absence when the subset asks for a MinKNOW section", () => {
    const { container } = render(
      <RunHealthPanel health={makeHealth()} sections={RUN_HEALTH_QC_SECTIONS} />,
    );

    expect(screen.getByText(en.mame.runHealth.noMinKnow)).toBeInTheDocument();
    expect(container.textContent ?? "").not.toContain("{{");
    expect(container.textContent ?? "").not.toContain("mame.");
  });

  it("stays silent when the subset asks for nothing MinKNOW supplies", () => {
    render(<RunHealthPanel health={makeHealth()} sections={["verdict-breakdown"]} />);

    expect(screen.queryByText(en.mame.runHealth.noMinKnow)).not.toBeInTheDocument();
  });

  it("keeps stating the absence for the whole dashboard", () => {
    render(<RunHealthPanel health={makeHealth()} />);

    expect(screen.getByText(en.mame.runHealth.noMinKnow)).toBeInTheDocument();
  });

  it("says nothing about MinKNOW once the raw run supplied a pore yield", () => {
    render(
      <RunHealthPanel
        health={makeHealth({ pore_yield_pct: 61.5 })}
        sections={RUN_HEALTH_QC_SECTIONS}
      />,
    );

    expect(screen.queryByText(en.mame.runHealth.noMinKnow)).not.toBeInTheDocument();
    expect(screen.getByText("61.5%")).toBeInTheDocument();
  });

  it("shows an unavailable reason instead of plotting a partial histogram as zero", () => {
    render(
      <RunHealthPanel
        health={makeHealth({
          file_size_distribution: { min: 12, p05: 13, p25: 14, median: 15, p75: 16, p95: 17 } as RunHealthData["file_size_distribution"],
        })}
        sections={["file-size"]}
      />,
    );
    expect(screen.getByText(en.mame.runHealth.qcNotMeasured)).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
