/**
 * AnalyzeStepView.test.tsx — analyze sub-step 마운트 어설션 (D2.4, Phase G #18)
 *
 * Phase G #18: analyze.health 폐지 — RunHealthPanel이 verdict/plate에 분산 흡수됨.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc", () => ({
  rpc: vi.fn(),
}));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/ui/Panel", () => ({
  DataPanel: ({
    children,
    className,
    title,
    scrollBody,
  }: {
    children: React.ReactNode;
    className?: string;
    title?: string;
    scrollBody?: boolean;
  }) => (
    <div
      data-testid="data-panel"
      data-class-name={className ?? ""}
      data-title={title ?? ""}
      data-scroll-body={scrollBody ? "true" : "false"}
    >
      {children}
    </div>
  ),
}));
// Kept real (inside the usual test-id wrapper): the run-duration readout that
// survives dismissing the completion popup lives on this widget, so stubbing it
// out would hide the very thing the duration tests assert.
vi.mock("@/components/mame/widgets/SummaryRow", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/mame/widgets/SummaryRow")>();
  return {
    SummaryRow: () => (
      <div data-testid="summary-row">
        <actual.SummaryRow />
      </div>
    ),
  };
});
vi.mock("@/components/mame/widgets/VerdictTable", () => ({
  VerdictTable: () => <div data-testid="verdict-table" />,
}));
vi.mock("@/components/mame/widgets/PlateView", () => ({
  PlateView: ({
    expanded,
    onToggleExpand,
  }: {
    expanded?: boolean;
    onToggleExpand?: () => void;
  }) => (
    <div data-testid="plate-view" data-expanded={String(!!expanded)}>
      <button type="button" data-testid="plate-toggle" onClick={onToggleExpand}>
        toggle
      </button>
    </div>
  ),
}));
vi.mock("@/components/mame/widgets/RunHealthPanel", () => ({
  RunHealthPanel: () => <div data-testid="run-health-panel" />,
}));
vi.mock("@/components/mame/panels/InputPanel", () => ({
  InputPanel: () => <div data-testid="input-panel" />,
}));
vi.mock("@/components/mame/panels/ParameterPanel", () => ({
  ParameterPanel: () => <div data-testid="parameter-panel" />,
}));
// Stubbed to its open/closed state: what matters on 2.1 is that the step can
// reach it, not what the dialog draws (that is its own test file).
vi.mock("@/components/mame/dialogs/JanusMappingDialog", () => ({
  JanusMappingDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="janus-mapping-dialog" /> : null,
}));

// react-resizable-panels: PanelGroup/Panel/PanelResizeHandle are passthrough wrappers
vi.mock("react-resizable-panels", () => ({
  PanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Panel: ({
    children,
    defaultSize,
    minSize,
  }: {
    children: React.ReactNode;
    defaultSize?: number;
    minSize?: number;
  }) => (
    <div data-testid="resizable-panel" data-default-size={defaultSize ?? ""} data-min-size={minSize ?? ""}>
      {children}
    </div>
  ),
  PanelResizeHandle: () => <div data-testid="resize-handle" />,
}));

import { AnalyzeStepView } from "./AnalyzeStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { DEFAULT_JANUS_SETTINGS } from "@/lib/mame/janusSettings";
import type {
  AnalyzeSummary,
  DistributionStats,
  RunHealthData,
  VerdictRecord,
} from "@/types/mame/models";

const fakeHealth: RunHealthData = {
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
};

const fakeVerdict: VerdictRecord = {
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
  n_mapq_failed: 2,
  n_no_call_aa: 0,
  n_span_failed: 8,
  source_path: "/data/NB01/barcode01.fastq",
  aa_sequence: "MKLVF89W",
  observed_nt_changes: ["T265G"],
  observed_aa_changes: ["F89W"],
  expected_mutations: ["F89W"],
  mutant_id: "F89W",
  verdict: "PASS",
  verdict_notes: "",
};

/** `_summarize(verdicts)` shape as the analyze response carries it. */
const summaryOf = (total: number): AnalyzeSummary => ({
  total,
  pass_count: total,
  ambiguous_count: 0,
  fail_count: 0,
});

const fakeDistributionStats: DistributionStats = {
  n_files: 0,
  file_size_kb: { min: 0, p05: 0, p25: 0, median: 0, p75: 0, p95: 0, max: 0, mean: 0, std: 0 },
  suggested_cutoff_kb: 50,
  suggested_method: "median_minus_2sigma",
  bimodal: false,
};

describe("AnalyzeStepView (Task #12, analyze.review)", () => {
  beforeEach(() => {
    useMameAppStore.setState({ currentMameSubStep: "analyze.review" });
  });

  it("analyze.review mounts SummaryRow + VerdictTable + PlateView (unified split)", () => {
    const { getByTestId } = render(<AnalyzeStepView />);
    expect(getByTestId("summary-row")).toBeTruthy();
    expect(getByTestId("verdict-table")).toBeTruthy();
    expect(getByTestId("plate-view")).toBeTruthy();
  });

  it("analyze.review toggles plate wrapper to fullscreen overlay (absolute inset-0 z-40) on expand", () => {
    render(<AnalyzeStepView />);
    const region = screen.getByRole("region", { name: "Expanded plate view" });
    // Default collapsed: no overlay classes, just h-full.
    expect(region.className).toContain("h-full");
    expect(region.className).not.toContain("absolute");
    // Click PlateView's toggle (forwarded onToggleExpand lifts plateExpanded).
    fireEvent.click(screen.getByTestId("plate-toggle"));
    expect(region.className).toContain("absolute");
    expect(region.className).toContain("inset-0");
    expect(region.className).toContain("z-40");
    expect(screen.getByTestId("plate-view")).toHaveAttribute("data-expanded", "true");
    // Toggle back collapses.
    fireEvent.click(screen.getByTestId("plate-toggle"));
    expect(region.className).toContain("h-full");
    expect(region.className).not.toContain("absolute");
  });

  it("analyze.review with runHealth mounts RunHealthPanel (per-plate verdict chart)", () => {
    const { getByTestId } = render(<AnalyzeStepView runHealth={fakeHealth} />);
    expect(getByTestId("run-health-panel")).toBeTruthy();
  });

  it("analyze.review gives verdict table and per-plate breakdown enough vertical space", () => {
    render(<AnalyzeStepView runHealth={fakeHealth} />);

    const panels = screen.getAllByTestId("data-panel");
    const verdictPanel = panels.find((panel) => panel.dataset.title === "Verdict table");
    const resizablePanels = screen.getAllByTestId("resizable-panel");

    expect(verdictPanel).toHaveAttribute("data-class-name", expect.stringContaining("min-h-[240px]"));
    expect(resizablePanels).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ dataset: expect.objectContaining({ defaultSize: "34", minSize: "18" }) }),
        expect.objectContaining({ dataset: expect.objectContaining({ defaultSize: "66", minSize: "30" }) }),
      ]),
    );
  });

  it("lets the per-plate breakdown scroll instead of clipping it", () => {
    render(<AnalyzeStepView runHealth={fakeHealth} />);

    const panels = screen.getAllByTestId("data-panel");
    const breakdownPanel = panels.find(
      (panel) => panel.dataset.title === "Per-plate verdict breakdown",
    );
    const platePanel = panels.find((panel) => panel.dataset.title === "Plate map");
    const verdictPanel = panels.find((panel) => panel.dataset.title === "Verdict table");

    // RunHealthPanel has no scroll container of its own, so the panel body has
    // to provide one: without it the chart is cut off with no way to reach it.
    expect(breakdownPanel).toHaveAttribute("data-scroll-body", "true");
    // A px floor would push the section past a splitter dragged below it.
    expect(breakdownPanel?.dataset.className).not.toContain("min-h-[240px]");
    // The panel body owns the overflow now; the outer section must not also
    // declare one, or the two overflow classes race in the stylesheet.
    expect(breakdownPanel?.dataset.className).not.toContain("overflow-");

    // Children that scroll themselves stay opted out (no nested scrollbars).
    expect(platePanel).toHaveAttribute("data-scroll-body", "false");
    expect(platePanel?.dataset.className).not.toContain("overflow-");
    expect(verdictPanel).toHaveAttribute("data-scroll-body", "false");
  });

  it("analyze.review without runHealth does not mount RunHealthPanel", () => {
    const { queryByTestId } = render(<AnalyzeStepView />);
    expect(queryByTestId("run-health-panel")).toBeNull();
  });

  it("moves from analyze.inputs to analyze.review after analysis succeeds", async () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      isAnalyzing: true,
      validationErrors: [],
      verdicts: [],
      summary: null,
    });
    render(<AnalyzeStepView />);

    act(() => {
      // `summary` lands with the verdicts: both come out of the same analyze
      // response (inputSlice setSummary + setVerdicts).
      useMameAppStore.setState({
        isAnalyzing: false,
        validationErrors: [],
        verdicts: [fakeVerdict],
        summary: summaryOf(1),
      });
    });

    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
  });
});

/**
 * Zero-result analysis: "never run" and "ran and produced nothing" must not
 * render the same blank view. Every count shown comes off the analyze response
 * (summary.total, distribution_stats.n_files, wells_with_reads, assigned_reads,
 * total_reads, passed_mapq, passed_coverage); a field the response did not carry
 * is not rendered at all, and a cause is named only where the counts prove it.
 */
describe("AnalyzeStepView (zero-result analysis)", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.review",
      isAnalyzing: false,
      validationErrors: [],
      verdicts: [],
      summary: null,
      distributionStats: null,
      analyzeYield: null,
      analyzeMessage: "",
    });
  });

  it("pre-run analyze.review keeps the result panels and shows no zero-result notice", () => {
    render(<AnalyzeStepView />);
    expect(screen.getByTestId("verdict-table")).toBeTruthy();
    expect(screen.getByTestId("plate-view")).toBeTruthy();
    expect(screen.queryByTestId("empty-analysis-notice")).toBeNull();
  });

  it("a run that finished with 0 verdicts replaces the panels with the notice and backend counts", () => {
    useMameAppStore.setState({
      summary: summaryOf(0),
      distributionStats: { ...fakeDistributionStats, n_files: 12 },
      analyzeYield: { assigned_reads: 0, wells_with_reads: 0 },
    });
    render(<AnalyzeStepView runHealth={fakeHealth} />);

    const notice = screen.getByTestId("empty-analysis-notice");
    expect(notice).toBeTruthy();
    // Not an error boundary: a completed run is a status, not a failure.
    expect(notice.getAttribute("role")).toBe("status");
    // The blank table/plate/chart are gone, replaced by the explanation.
    expect(screen.queryByTestId("verdict-table")).toBeNull();
    expect(screen.queryByTestId("plate-view")).toBeNull();
    expect(screen.queryByTestId("run-health-panel")).toBeNull();
    // Reported counts, straight off the response fields.
    expect(screen.getByText("Input files")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("Wells with reads")).toBeTruthy();
    expect(screen.getByText("Assigned reads")).toBeTruthy();
    // Actionable reason, not just an empty panel.
    expect(screen.getByText(/reference file matches the sequenced amplicon/i)).toBeTruthy();
  });

  it("omits demux counts the response did not carry (consensus-dir mode)", () => {
    useMameAppStore.setState({
      summary: summaryOf(0),
      distributionStats: { ...fakeDistributionStats, n_files: 3 },
      analyzeYield: null,
    });
    render(<AnalyzeStepView />);

    expect(screen.getByTestId("empty-analysis-notice")).toBeTruthy();
    expect(screen.getByText("Input files")).toBeTruthy();
    expect(screen.queryByText("Wells with reads")).toBeNull();
    expect(screen.queryByText("Assigned reads")).toBeNull();
    // No gate counters either, and with no counts there is no cause to name.
    expect(screen.queryByText("Reads in fastq_pass")).toBeNull();
    expect(screen.queryByText("Reads passing MAPQ")).toBeNull();
    expect(screen.queryByTestId("zero-result-cause")).toBeNull();
    // The checklist stays: it is what remains when nothing can be concluded.
    expect(screen.getByText(/reference file matches the sequenced amplicon/i)).toBeTruthy();
  });

  it("names the reference mismatch when reads existed and none cleared MAPQ", () => {
    useMameAppStore.setState({
      summary: summaryOf(0),
      distributionStats: { ...fakeDistributionStats, n_files: 12 },
      analyzeYield: {
        assigned_reads: 0,
        wells_with_reads: 0,
        total_reads: 48000,
        passed_mapq: 0,
        passed_coverage: 0,
      },
    });
    render(<AnalyzeStepView />);

    const cause = screen.getByTestId("zero-result-cause");
    expect(cause.getAttribute("data-cause")).toBe("noAlignment");
    // The count in the sentence is the response field, not a fixed string.
    expect(cause.textContent).toContain((48000).toLocaleString());
    expect(cause.textContent).toMatch(/none of them aligned to the reference/i);
    // Gate counters render as their own rows.
    expect(screen.getByText("Reads in fastq_pass")).toBeTruthy();
    expect(screen.getByText("Reads passing MAPQ")).toBeTruthy();
    expect(screen.getByText("Reads passing coverage")).toBeTruthy();
  });

  it("names the coverage gate when reads aligned but none cleared coverage", () => {
    useMameAppStore.setState({
      summary: summaryOf(0),
      distributionStats: { ...fakeDistributionStats, n_files: 12 },
      analyzeYield: {
        assigned_reads: 0,
        wells_with_reads: 0,
        total_reads: 48000,
        passed_mapq: 31500,
        passed_coverage: 0,
      },
    });
    render(<AnalyzeStepView />);

    const cause = screen.getByTestId("zero-result-cause");
    expect(cause.getAttribute("data-cause")).toBe("noCoverage");
    expect(cause.textContent).toContain((31500).toLocaleString());
    expect(cause.textContent).toMatch(/covered enough of it to be called/i);
    // Distinct from the alignment case, not the same sentence with new numbers.
    expect(cause.textContent).not.toMatch(/none of them aligned to the reference/i);
  });

  it("claims no cause when the run simply had no reads to begin with", () => {
    useMameAppStore.setState({
      summary: summaryOf(0),
      distributionStats: { ...fakeDistributionStats, n_files: 12 },
      analyzeYield: { total_reads: 0, passed_mapq: 0, passed_coverage: 0 },
    });
    render(<AnalyzeStepView />);

    // total_reads == 0 rules both gates out as explanations: nothing reached them.
    expect(screen.queryByTestId("zero-result-cause")).toBeNull();
    expect(screen.getByText("Reads in fastq_pass")).toBeTruthy();
    expect(screen.getByText(/barcode folders contain reads/i)).toBeTruthy();
  });

  it("a run that produced verdicts keeps the result panels and shows no notice", () => {
    useMameAppStore.setState({
      summary: summaryOf(1),
      distributionStats: { ...fakeDistributionStats, n_files: 12 },
      verdicts: [fakeVerdict],
    });
    render(<AnalyzeStepView runHealth={fakeHealth} />);

    expect(screen.queryByTestId("empty-analysis-notice")).toBeNull();
    expect(screen.getByTestId("verdict-table")).toBeTruthy();
    expect(screen.getByTestId("plate-view")).toBeTruthy();
  });

  it("analyze.inputs replaces the completion message when the run produced 0 verdicts", () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      analyzeMessage: "Analysis complete",
      summary: summaryOf(0),
    });
    render(<AnalyzeStepView />);

    expect(screen.queryByText("Analysis complete")).toBeNull();
    expect(screen.getByText("Analysis finished, but produced no results")).toBeTruthy();
    expect(screen.getByTestId("empty-analysis-notice")).toBeTruthy();
  });

  it("does not pop the duration dialog for a run that produced 0 verdicts", async () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      isAnalyzing: true,
      analyzeDurationMs: null,
    });
    render(<AnalyzeStepView />);

    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        validationErrors: [],
        verdicts: [],
        summary: summaryOf(0),
        analyzeDurationMs: 192_000,
      });
    });

    // EmptyAnalysisNotice owns this outcome; a modal on top of it would have to
    // be dismissed before the explanation could be read.
    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
    expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
    expect(screen.getByTestId("empty-analysis-notice")).toBeTruthy();
  });

  it("still moves to analyze.review when a run finishes with 0 verdicts", async () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      isAnalyzing: true,
      summary: null,
    });
    render(<AnalyzeStepView />);

    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        validationErrors: [],
        verdicts: [],
        summary: summaryOf(0),
      });
    });

    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
  });
});

/**
 * Step 2.1 completion popup: how long the run took.
 *
 * `analyzeDurationMs` is written only where a run applies its response, so the
 * popup keys on its null -> number edge. That edge is what separates a finished
 * run from a cancelled one: cancelling a re-run leaves the previous run's
 * `summary` in place, so `summary` alone would fire the popup on cancel.
 */
describe("AnalyzeStepView (run duration popup)", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      isAnalyzing: false,
      validationErrors: [],
      verdicts: [],
      summary: null,
      analyzeDurationMs: null,
      analyzeMessage: "",
    });
  });

  /** Drive one successful run to completion from a mounted 2.1 view. */
  function finishRun(durationMs: number) {
    act(() => {
      useMameAppStore.setState({ isAnalyzing: true, analyzeDurationMs: null });
    });
    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        validationErrors: [],
        verdicts: [fakeVerdict],
        summary: summaryOf(1),
        analyzeDurationMs: durationMs,
      });
    });
  }

  it("pops the elapsed time when a run finishes with results", async () => {
    render(<AnalyzeStepView />);
    finishRun(192_000);

    const dialog = await screen.findByTestId("analyze-duration-dialog");
    expect(dialog).toBeTruthy();
    // 192 s = 3 min 12 s: minutes lead, seconds are kept because they are not 0.
    expect(screen.getByTestId("analyze-duration-value").textContent).toBe("3 min 12 s");
    // The popup must not undo the 2.1 -> 2.2 hand-off.
    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
  });

  it("reports a sub-minute run in seconds alone, not as 0 minutes", async () => {
    render(<AnalyzeStepView />);
    finishRun(47_400);

    await screen.findByTestId("analyze-duration-dialog");
    expect(screen.getByTestId("analyze-duration-value").textContent).toBe("47 s");
  });

  it("drops the trailing seconds on a whole-minute run", async () => {
    render(<AnalyzeStepView />);
    finishRun(120_000);

    await screen.findByTestId("analyze-duration-dialog");
    expect(screen.getByTestId("analyze-duration-value").textContent).toBe("2 min");
  });

  it("stays closed when the run is cancelled", async () => {
    // A previous successful run leaves verdicts and a summary behind; only the
    // duration being cleared marks this run as one that never completed.
    useMameAppStore.setState({ verdicts: [fakeVerdict], summary: summaryOf(1) });
    render(<AnalyzeStepView />);

    act(() => {
      useMameAppStore.setState({ isAnalyzing: true, analyzeDurationMs: null });
    });
    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        analyzeMessage: "Analysis cancelled",
        analyzeDurationMs: null,
      });
    });

    await waitFor(() => {
      expect(useMameAppStore.getState().isAnalyzing).toBe(false);
    });
    expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
  });

  it("stays closed when the run fails", async () => {
    render(<AnalyzeStepView />);

    act(() => {
      useMameAppStore.setState({ isAnalyzing: true, analyzeDurationMs: null });
    });
    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        analyzeMessage: "Analysis failed",
        analyzeDurationMs: null,
        validationErrors: ["sidecar exploded"],
      });
    });

    await waitFor(() => {
      expect(useMameAppStore.getState().isAnalyzing).toBe(false);
    });
    expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
  });

  it("pops once per run and does not come back after it is closed", async () => {
    render(<AnalyzeStepView />);
    finishRun(192_000);

    await screen.findByTestId("analyze-duration-dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
    });

    // Unrelated store traffic re-renders the view; the duration is unchanged,
    // so the dialog must not reappear.
    act(() => {
      useMameAppStore.setState({ analyzeMessage: "Analysis complete" });
    });
    act(() => {
      useMameAppStore.setState({ analyzeProgress: 100 });
    });
    expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
  });

  it("leaves the elapsed time on the 2.2 SummaryRow after the popup is closed", async () => {
    render(<AnalyzeStepView />);
    finishRun(192_000);

    await screen.findByTestId("analyze-duration-dialog");
    // Same run, same formatter: popup and SummaryRow cannot disagree.
    expect(screen.getByText("Took 3 min 12 s")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
    });

    // The popup is gone; the readout is not. That is the whole point of it.
    expect(screen.getByTestId("summary-row").textContent).toContain("Took 3 min 12 s");
  });

  it("shows no elapsed-time item on 2.2 before a run has finished", () => {
    useMameAppStore.setState({ currentMameSubStep: "analyze.review" });
    render(<AnalyzeStepView />);

    // Absent, not filled with a placeholder duration.
    expect(screen.getByTestId("summary-row")).toBeTruthy();
    expect(screen.queryByText(/^Took /)).toBeNull();
  });

  it("shows no elapsed-time item on 2.2 for a cancelled run", async () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.review",
      verdicts: [fakeVerdict],
      summary: summaryOf(1),
    });
    render(<AnalyzeStepView />);

    act(() => {
      useMameAppStore.setState({ isAnalyzing: true, analyzeDurationMs: null });
    });
    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        analyzeMessage: "Analysis cancelled",
        analyzeDurationMs: null,
      });
    });

    await waitFor(() => {
      expect(useMameAppStore.getState().isAnalyzing).toBe(false);
    });
    expect(screen.queryByText(/^Took /)).toBeNull();
  });

  it("does not reopen for a duration that was already on the store at mount", () => {
    useMameAppStore.setState({
      verdicts: [fakeVerdict],
      summary: summaryOf(1),
      analyzeDurationMs: 192_000,
    });
    render(<AnalyzeStepView />);

    expect(screen.queryByTestId("analyze-duration-dialog")).toBeNull();
  });
});

/**
 * Janus instrument settings on 2.1.
 *
 * The File menu item that used to open the dialog was removed in v0.14.7, which
 * left the liquid class and the deck rack numbers with no reachable input on the
 * screen that collects the run's other inputs. They stay optional: the two files
 * a run writes need none of them, except the transfer volume, which is the one
 * value nothing can derive and which therefore sits on the step itself.
 */
describe("AnalyzeStepView (Janus settings entry point)", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      isAnalyzing: false,
      isValidating: false,
      validationErrors: [],
      summary: null,
      verdicts: [],
      analyzeDurationMs: null,
      janusSettings: DEFAULT_JANUS_SETTINGS,
    });
  });

  it("opens the Janus settings from the inputs step", () => {
    render(<AnalyzeStepView />);
    expect(screen.queryByTestId("janus-mapping-dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Open Janus instrument settings" }));

    expect(screen.getByTestId("janus-mapping-dialog")).toBeTruthy();
  });

  it("reaches the settings before a run, when there is nothing to export yet", () => {
    render(<AnalyzeStepView />);

    expect(
      screen.getByRole("button", { name: "Open Janus instrument settings" }),
    ).toBeEnabled();
  });

  it("puts the transfer volume on the inputs step, labelled as an assumption", () => {
    // The one instrument value nothing can derive: the deck numbers come from
    // the plates of the run and the liquid class ships blank, so volume is all
    // the operator has to decide before the run writes its instrument sheet.
    render(<AnalyzeStepView />);

    const field = screen.getByLabelText(/Transfer volume/i) as HTMLInputElement;
    expect(field.value).toBe("100");
    expect(screen.getByText(/assumption with no lab source/i)).toBeTruthy();

    fireEvent.change(field, { target: { value: "45" } });

    expect(useMameAppStore.getState().janusSettings.volume).toBe(45);
  });

  it("leaves the run enabled while the instrument settings are unset", () => {
    useMameAppStore.setState({
      inputMode: "sorted_barcode",
      inputDir: "/data/consensus",
      expectedPath: "/data/kuro.xlsx",
      referencePath: "/data/ref.fasta",
      outputPath: "/data/out.xlsx",
      janusSettings: { ...useMameAppStore.getState().janusSettings, liquidClass: "" },
    });
    render(<AnalyzeStepView />);

    expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
  });
});
