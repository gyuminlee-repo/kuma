import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "@/store/appStore";
import { strictSpatialContextKey } from "@/lib/strictSpatial";
import { distinctSpatial95Fixture } from "@/test-utils/strictSpatialFixture";
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
