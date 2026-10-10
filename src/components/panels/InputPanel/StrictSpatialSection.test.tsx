import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "@/store/appStore";
import { strictSpatialContextKey } from "@/lib/strictSpatial";
import { distinctSpatial95Fixture, syntheticFullDfTestFixture } from "@/test-utils/strictSpatialFixture";
import { StrictSpatialSection } from "./StrictSpatialSection";

beforeEach(() => {
  useAppStore.setState({ strictSpatialEnabled: true, structuralDiversityEnabled: true,
    strictSpatialBudgetMode: "unique_sites", strictSpatialSiteCap: null, strictSpatialSelection: null, strictSpatialError: null,
    evolveproMode: "pipeline", mutationInputMode: "evolvepro", evolveproCsvPath: "", maxPrimers: 95 });
});
afterEach(() => useAppStore.getState().cancelDiversityReload());

describe("strict spatial budget controls", () => {
  it("defaults to one variant per site and exposes a distinct budget with optional positive cap", () => {
    render(<StrictSpatialSection />);
    const budget = screen.getByRole("combobox", { name: "Selection budget" });
    expect(budget).toHaveValue("unique_sites");
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    fireEvent.change(budget, { target: { value: "distinct_variants" } });
    const cap = screen.getByRole("spinbutton", { name: "Maximum variants per site" });
    expect(cap).toHaveValue(null);
    expect(screen.getByText(/N counts distinct variants/)).toBeInTheDocument();
    fireEvent.change(cap, { target: { value: "19" } });
    expect(useAppStore.getState().strictSpatialSiteCap).toBe(19);
    fireEvent.change(cap, { target: { value: "0" } });
    expect(useAppStore.getState().strictSpatialSiteCap).toBe(19);
    expect(cap).toHaveValue(19);
    expect(screen.getByRole("alert")).toHaveTextContent("positive whole number");
    fireEvent.change(cap, { target: { value: "" } });
    expect(useAppStore.getState().strictSpatialSiteCap).toBeNull();
  });

  it("reports 95 variants and five unique sites separately and clears the evidence after a cap edit", () => {
    const report = distinctSpatial95Fixture();
    useAppStore.setState({ strictSpatialBudgetMode: "distinct_variants", evolveproSelectedVariants: report.selected_variants });
    useAppStore.setState({ strictSpatialSelection: { result: report, contextKey: strictSpatialContextKey(useAppStore.getState()) } });
    render(<StrictSpatialSection />);
    expect(screen.getByRole("status")).toHaveTextContent("95 selected variants across 5 unique sites");
    expect(screen.getByText("95 eligible variants across 5 unique sites.")).toBeInTheDocument();
    expect(screen.getByText(/Budget: Distinct variants; per-site limit: Unlimited/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "19" } });
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Load or reselect");
  });
});

describe("full df_test pool diagnostics", () => {
  function setReport(report: ReturnType<typeof syntheticFullDfTestFixture>) {
    useAppStore.setState({ maxPrimers: report.requested_count, strictSpatialBudgetMode: "distinct_variants",
      evolveproScoreOrder: report.score_order, evolveproSelectedVariants: report.selected_variants,
      evolveproCsvPath: "/tmp/synthetic_df_test.csv" });
    useAppStore.setState({ strictSpatialSelection: { result: report, contextKey: strictSpatialContextKey(useAppStore.getState()) } });
  }

  it.each([1, 12, 95, 100])("shows the requested N=%s against the complete synthetic prediction pool", (count) => {
    const report = syntheticFullDfTestFixture(count);
    setReport(report);
    render(<StrictSpatialSection />);
    expect(screen.getByRole("status")).toHaveTextContent(`${count} selected variants across ${report.selected_site_count} unique sites`);
    expect(screen.getByText("114 eligible variants across 6 unique sites.")).toBeInTheDocument();
    expect(screen.getByText(/Load the full EVOLVEpro df_test prediction CSV, then set N/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Selected vs. score Top-N" });
    const counts = within(table).getByRole("row", { name: `Distinct variants ${count} ${count}` });
    expect(within(counts).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([String(count), String(count)]);
  });

  it("distinguishes spread selection from score Top-N without implying a fitness benefit", () => {
    setReport(syntheticFullDfTestFixture(12));
    render(<StrictSpatialSection />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("row", { name: "Unique sites 6 1" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Max. variants per site 2 12" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Min. site separation (Å) 4 N/A" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Mean nearest-site distance (Å) 0 10" })).toBeInTheDocument();
    expect(screen.getByText(/equal weight per site/)).toBeInTheDocument();
    expect(screen.getByText(/higher is better.*ties share an averaged rank/)).toBeInTheDocument();
    expect(screen.getByText(/not measured fitness loss or biological benefit/)).toBeInTheDocument();
    expect(screen.getByText(/Overlap: 2\/12 variants/)).toBeInTheDocument();
  });

  it("labels ascending score order and keeps its direction-aware gap", () => {
    setReport(syntheticFullDfTestFixture(12, true, "asc"));
    render(<StrictSpatialSection />);
    expect(screen.getByText(/lower is better.*Rank 1 is best/)).toBeInTheDocument();
    expect(screen.getByText(/Raw-score mean gap to Top-N: 42.5/)).toBeInTheDocument();
  });

  it("renders integer count metrics exactly even above four significant digits", () => {
    const report = syntheticFullDfTestFixture(12);
    if (!report.comparison || !report.comparison.top_n) throw Error("Expected scored fixture");
    // A presentation-only boundary stub; IPC accounting has its own validator tests.
    const counts = { variant_count: 12345, site_count: 12345, max_variants_per_site: 1 };
    setReport({ ...report, comparison: { ...report.comparison,
      selected: { ...report.comparison.selected, ...counts }, top_n: { ...report.comparison.top_n, ...counts } } });
    render(<StrictSpatialSection />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("row", { name: "Distinct variants 12345 12345" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Unique sites 12345 12345" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Max. variants per site 1 1" })).toBeInTheDocument();
  });

  it("shows an unavailable overflowing score summary without hiding selection or rank", () => {
    const report = syntheticFullDfTestFixture(12);
    if (!report.comparison) throw Error("Expected comparison fixture");
    setReport({ ...report, comparison: { ...report.comparison,
      selected: { ...report.comparison.selected, score_mean: null }, score_gap_to_top_n: null } });
    render(<StrictSpatialSection />);
    expect(screen.getByText(/Raw-score mean gap to Top-N: N\/A/)).toBeInTheDocument();
    expect(screen.getByText(/cannot be represented reliably/)).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByRole("row", { name: "Mean score rank 49 6.5" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("12 selected variants");
  });

  it("retains selected geometry but marks missing score diagnostics unavailable", () => {
    setReport(syntheticFullDfTestFixture(12, false));
    render(<StrictSpatialSection />);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("row", { name: "Unique sites 6 N/A" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Mean raw score N/A N/A" })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: "Mean score rank N/A N/A" })).toBeInTheDocument();
    expect(screen.getByText(/score Top-N, score means, ranks and score gap cannot be computed/)).toBeInTheDocument();
    expect(screen.queryByText(/Raw-score mean gap to Top-N:/)).not.toBeInTheDocument();
  });

  it("keeps older verified certificates usable without inventing diagnostics", () => {
    setReport({ ...syntheticFullDfTestFixture(12), comparison: undefined });
    render(<StrictSpatialSection />);
    expect(screen.getByRole("status")).toHaveTextContent("12 selected variants");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
