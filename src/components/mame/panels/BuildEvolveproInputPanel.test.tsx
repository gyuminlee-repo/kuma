/**
 * BuildEvolveproInputPanel: source-mode toggle and client-side input gating.
 *
 * The panel must send rank-mode params (gc_data_xlsx) or reports-mode params
 * (remeasure_report_xlsx + exactly one round-1 source), never a mix, and must
 * block the build when the selected mode is missing a required file rather than
 * letting the backend _mode_xor validator reject it.
 */

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockSetBuildEvolveproCompletion = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
  save: vi.fn(),
}));
vi.mock("@/lib/ipc-mame", () => ({
  buildEvolveproInput: vi.fn(),
}));
vi.mock("@/lib/openFolder", () => ({
  revealInOSFolder: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("@/store/mame/mameAppStore", () => ({
  useMameAppStore: (
    selector: (s: {
      resetEpoch: number;
      setBuildEvolveproCompletion: typeof mockSetBuildEvolveproCompletion;
    }) => unknown,
  ) =>
    selector({
      resetEpoch: 0,
      setBuildEvolveproCompletion: mockSetBuildEvolveproCompletion,
    }),
}));

import { buildEvolveproInput } from "@/lib/ipc-mame";
import {
  BUILD_EVOLVEPRO_STORAGE_KEY,
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  type BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";
import { BuildEvolveproInputPanel } from "./BuildEvolveproInputPanel";

const mockBuild = vi.mocked(buildEvolveproInput);

function seed(partial: Partial<BuildEvolveproFormState>): void {
  const state: BuildEvolveproFormState = {
    ...BUILD_EVOLVEPRO_DEFAULT_STATE,
    ...partial,
  };
  localStorage.setItem(BUILD_EVOLVEPRO_STORAGE_KEY, JSON.stringify(state));
}

const RESULT = {
  output_path: "/out/ep.xlsx",
  mode: "rank" as const,
  n_variants: 3,
  n_authoritative: 3,
  n_fallback_only: 0,
  mapping_audit: [],
  mapping_audit_path: "/out/ep.xlsx.mapping.json",
  n_ngs_excluded: 0,
  ngs_excluded: [],
  prev_descending: true,
  warnings: [],
  swap_warnings: [],
  mismatched: [],
};

const BUILD_LABEL = "Build EVOLVEpro input";

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mockBuild.mockResolvedValue(RESULT);
});

describe("BuildEvolveproInputPanel source-mode toggle", () => {
  it("defaults to rank mode and names the missing required files", () => {
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    const missing = screen.getByText(/Still needed/);
    expect(missing.textContent).toContain("Plate layout xlsx");
    expect(missing.textContent).toContain("GC data xlsx");
    expect(missing.textContent).toContain("Output EVOLVEpro xlsx");
  });

  it("focuses the matching field when a missing input is clicked", () => {
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Plate layout xlsx" }));

    expect(screen.getByLabelText("Plate layout xlsx")).toHaveFocus();
  });

  it("can clear restored EVOLVEpro input paths without clearing the whole Mame project", () => {
    seed({
      layoutXlsx: "/in/layout.xlsx",
      gcDataXlsx: "/in/gc.xlsx",
      outputXlsx: "/out/ep.xlsx",
    });

    render(<BuildEvolveproInputPanel />);

    expect(screen.getByText("layout.xlsx")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear restored EVOLVEpro inputs" }));

    expect(screen.queryByText("layout.xlsx")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
  });

  it("sends rank-mode params with no reports-mode fields", async () => {
    seed({
      layoutXlsx: "/in/layout.xlsx",
      gcDataXlsx: "/in/gc.xlsx",
      outputXlsx: "/out/ep.xlsx",
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      layout_xlsx: "/in/layout.xlsx",
      gc_data_xlsx: "/in/gc.xlsx",
      rep_batch_xlsx: undefined,
      prev_evolvepro_xlsx: undefined,
      output_xlsx: "/out/ep.xlsx",
    });
    expect(mockSetBuildEvolveproCompletion).toHaveBeenLastCalledWith({
      outputPath: "/out/ep.xlsx",
      signature:
        "{\"sourceMode\":\"rank\",\"round1Source\":\"prev\",\"layoutXlsx\":\"/in/layout.xlsx\",\"gcDataXlsx\":\"/in/gc.xlsx\",\"repBatchXlsx\":\"\",\"prevEvolveproXlsx\":\"\",\"round1ReportXlsx\":\"\",\"round1EvolveproXlsx\":\"\",\"remeasureReportXlsx\":\"\",\"verdictXlsx\":\"\",\"outputXlsx\":\"/out/ep.xlsx\"}",
    });
  });

  it("swaps the visible file pickers when reports mode is selected", () => {
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByLabelText("GC data xlsx")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Raw Agilent reports" }));

    expect(screen.queryByLabelText("GC data xlsx")).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Re-measure report xlsx (variant-labeled)"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: "Previous EVOLVEpro" }),
    ).toHaveAttribute("aria-checked", "true");
  });

  it("sends the previous-EVOLVEpro round-1 source in reports mode", async () => {
    seed({
      sourceMode: "reports",
      round1Source: "prev",
      round1EvolveproXlsx: "/in/round1_ep.xlsx",
      remeasureReportXlsx: "/in/remeasure.xlsx",
      outputXlsx: "/out/ep.xlsx",
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      round1_evolvepro_xlsx: "/in/round1_ep.xlsx",
      layout_xlsx: undefined,
      remeasure_report_xlsx: "/in/remeasure.xlsx",
      verdict_xlsx: undefined,
      output_xlsx: "/out/ep.xlsx",
    });
  });

  it("blocks a raw round-1 report build until the plate layout is chosen", () => {
    seed({
      sourceMode: "reports",
      round1Source: "raw",
      round1ReportXlsx: "/in/round1_report.xlsx",
      remeasureReportXlsx: "/in/remeasure.xlsx",
      outputXlsx: "/out/ep.xlsx",
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    expect(screen.getByText(/Still needed/).textContent).toContain(
      "Plate layout xlsx",
    );
    expect(mockBuild).not.toHaveBeenCalled();
  });

  it("sends the raw round-1 report with its layout once complete", async () => {
    seed({
      sourceMode: "reports",
      round1Source: "raw",
      layoutXlsx: "/in/layout.xlsx",
      round1ReportXlsx: "/in/round1_report.xlsx",
      remeasureReportXlsx: "/in/remeasure.xlsx",
      verdictXlsx: "/in/verdict.xlsx",
      outputXlsx: "/out/ep.xlsx",
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      layout_xlsx: "/in/layout.xlsx",
      round1_report_xlsx: "/in/round1_report.xlsx",
      remeasure_report_xlsx: "/in/remeasure.xlsx",
      verdict_xlsx: "/in/verdict.xlsx",
      output_xlsx: "/out/ep.xlsx",
    });
  });
});
