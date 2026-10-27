import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRoundStore } from "@/store/round/roundSlice";
import { ProjectProvider } from "@/state/projectContext";

const mockMameState = vi.hoisted(() => ({
  resetEpoch: 0,
  buildEvolveproSeedEpoch: 0,
  analyzeResult: null,
  wells: [],
}));
const mockSetCompletion = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: vi.fn().mockResolvedValue(undefined) }));
vi.mock("@/lib/ipc-mame", () => ({
  buildEvolveproInput: vi.fn(),
  detectMeasurementSource: vi.fn(),
  previewGcRows: vi.fn(),
}));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("@/lib/workspace", () => ({ registerArtifacts: vi.fn().mockResolvedValue(undefined) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/store/mame/mameAppStore", () => ({
  resequenceStore: (selector: (state: { analyzeResult: null; wells: never[] }) => unknown) =>
    selector({ analyzeResult: null, wells: [] }),
  useMameAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ ...mockMameState, setBuildEvolveproCompletion: mockSetCompletion }),
}));

import { open } from "@tauri-apps/plugin-dialog";
import { buildEvolveproInput, previewGcRows } from "@/lib/ipc-mame";
import {
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  loadBuildEvolveproFromStorage,
  saveBuildEvolveproToStorage,
  type BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";
import { toExcludedRow } from "@/lib/mame/gcRowReview";
import type { BuildEvolveproInputResult, PreviewGcRow } from "@/types/mame/build_evolvepro_input";
import { BuildEvolveproInputPanel } from "./BuildEvolveproInputPanel";

const PROJECT = "/project";
const OUTPUT = "/project/activity/evolvepro_input.xlsx";
const LAYOUT = "/project/layout.xlsx";

function row(overrides: Partial<PreviewGcRow>): PreviewGcRow {
  return {
    source: "round1_report_xlsx",
    block_index: 1,
    row_index: 2,
    sample_name: "5F",
    area: 100,
    kind: "variant",
    status: "used",
    reason: null,
    detail: "",
    flags: [],
    ...overrides,
  };
}

const USED = row({ row_index: 2, sample_name: "5F" });
const USED_2 = row({ row_index: 3, sample_name: "10L" });
const WT = row({ row_index: 4, sample_name: "WT", kind: "wt", status: "wt" });
const BLANK = row({ row_index: 5, sample_name: "BLANK", status: "set_aside", reason: "non_well_sample" });
const ROWS = [USED, USED_2, WT, BLANK];

const RESULT: BuildEvolveproInputResult = {
  output_path: OUTPUT,
  n_variants: 2,
  n_authoritative: 2,
  n_fallback_only: 0,
  warnings: [],
  mismatched: [],
  n_ngs_excluded: 0,
  ngs_excluded: [],
  gc_export_path: "",
  label_audit: null,
  manifest_path: `${OUTPUT}.manifest.json`,
  primary_format: "round1_report_xlsx",
  input_count: 2,
  evaluable_count: 2,
  exclusion_reason_counts: { non_well_sample: 1, operator_excluded: 1 },
  normalization_sources: [],
  evidence_hash: "sha256:evidence",
  artifact_hashes: {},
  wt_values: [1],
  variant_replicates: { "10L": [0.6] },
  excluded_rows: [
    { source: "round1_report_xlsx", block_index: 1, row_index: 2, sample_name: "5F", area: 100, reason: "operator_excluded", kept: false },
  ],
  wt_rows: [
    { source: "round1_report_xlsx", block_index: 1, row_index: 4, sample_name: "WT", area: 100 },
  ],
};

function form(overrides: Partial<BuildEvolveproFormState> = {}): BuildEvolveproFormState {
  return {
    ...BUILD_EVOLVEPRO_DEFAULT_STATE,
    primarySource: "rawReport",
    round1ReportXlsx: "/project/report.xlsx",
    layoutXlsx: LAYOUT,
    verdictXlsx: "/project/ngs/verdict.xlsx",
    outputXlsx: OUTPUT,
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}>
      <BuildEvolveproInputPanel />
    </ProjectProvider>,
  );
}

const BUILD_BUTTON = { name: "Convert to EVOLVEpro input format" };
const WT_REFUSAL = "round1_report_xlsx has no WT block areas";

/**
 * The mocked build's answer for a selection. It refuses only when WT is gone,
 * like a raw report does; the screen must show this answer and nothing of its own.
 */
let refusalFor: (excluded: readonly { row_index: number }[]) => string | null = (excluded) =>
  excluded.some((row) => row.row_index === WT.row_index) ? WT_REFUSAL : null;

async function reviewLoaded(): Promise<void> {
  await screen.findByRole("checkbox", { name: "Use 5F at block 1, row 2" });
}

beforeEach(() => {
  refusalFor = (excluded) => (excluded.some((row) => row.row_index === WT.row_index) ? WT_REFUSAL : null);
  localStorage.clear();
  useRoundStore.setState({ rounds: [], active_round_id: null });
  vi.clearAllMocks();
  vi.mocked(buildEvolveproInput).mockResolvedValue(RESULT);
  vi.mocked(previewGcRows).mockImplementation(async (params) => ({
    rows: ROWS,
    refusal: null,
    selection_refusal: refusalFor(params.excluded_rows ?? []),
  }));
});
afterEach(cleanup);

describe("BuildEvolveproInputPanel row review", () => {
  it("reads the rows with the build's inputs and the saved selection", async () => {
    saveBuildEvolveproToStorage(form({ excludedRows: [toExcludedRow(USED)] }), PROJECT);
    renderPanel();
    await reviewLoaded();
    expect(previewGcRows).toHaveBeenCalledWith(
      expect.objectContaining({
        round1_report_xlsx: "/project/report.xlsx",
        layout_xlsx: LAYOUT,
        verdict_xlsx: "/project/ngs/verdict.xlsx",
        excluded_rows: [toExcludedRow(USED)],
      }),
    );
  });

  it("does not read rows before the inputs are chosen", () => {
    saveBuildEvolveproToStorage(form({ verdictXlsx: "" }), PROJECT);
    renderPanel();
    expect(previewGcRows).not.toHaveBeenCalled();
    expect(screen.getByText(/Choose the measurement file/)).toBeInTheDocument();
  });

  it("keeps the build closed while the rows are being read", async () => {
    let resolve: (value: Awaited<ReturnType<typeof previewGcRows>>) => void = () => undefined;
    vi.mocked(previewGcRows).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    expect(screen.getByRole("button", BUILD_BUTTON)).toBeDisabled();
    expect(screen.getByRole("status", { name: "Why the build cannot run" })).toHaveTextContent("The rows are still being read");
    fireEvent.click(screen.getByRole("button", BUILD_BUTTON));
    expect(buildEvolveproInput).not.toHaveBeenCalled();
    resolve({ rows: ROWS, refusal: null, selection_refusal: null });
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
  });

  it("keeps the build closed when the rows could not be read, until they are read again", async () => {
    vi.mocked(previewGcRows).mockRejectedValueOnce(new Error("file is open in Excel"));
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    const retry = await screen.findByRole("button", { name: "Read again" });
    expect(screen.getByRole("button", BUILD_BUTTON)).toBeDisabled();
    expect(screen.getByRole("status", { name: "Why the build cannot run" })).toHaveTextContent("could not be read");
    fireEvent.click(screen.getByRole("button", BUILD_BUTTON));
    expect(buildEvolveproInput).not.toHaveBeenCalled();
    fireEvent.click(retry);
    await reviewLoaded();
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
    expect(previewGcRows).toHaveBeenCalledTimes(2);
  });

  it("asks the build about an untick and sends it as excluded_rows", async () => {
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    await reviewLoaded();
    fireEvent.click(screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" }));
    expect(screen.getByRole("button", BUILD_BUTTON)).toBeDisabled();
    expect(screen.getByRole("status", { name: "Why the build cannot run" })).toHaveTextContent("Checking the rows you unticked");
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
    expect(previewGcRows).toHaveBeenLastCalledWith(expect.objectContaining({ excluded_rows: [toExcludedRow(USED)] }));
    fireEvent.click(screen.getByRole("button", BUILD_BUTTON));
    await waitFor(() => expect(buildEvolveproInput).toHaveBeenCalledTimes(1));
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ excluded_rows: [toExcludedRow(USED)] }),
    );
    expect(loadBuildEvolveproFromStorage(PROJECT).excludedRows).toEqual([toExcludedRow(USED)]);
  });

  it("sends nothing excluded when every row keeps its default tick", async () => {
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    await reviewLoaded();
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
    fireEvent.click(screen.getByRole("button", BUILD_BUTTON));
    await waitFor(() => expect(buildEvolveproInput).toHaveBeenCalledTimes(1));
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({ excluded_rows: [] }));
  });

  it("blocks the build with the build's own refusal for the selection", async () => {
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    await reviewLoaded();
    fireEvent.click(screen.getByRole("checkbox", { name: "Use WT at block 1, row 4" }));
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "Why the build cannot run" })).toHaveTextContent(
        "The build refuses the rows as ticked: Raw Agilent report has no WT block areas",
      ),
    );
    expect(screen.getByRole("button", BUILD_BUTTON)).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Use WT at block 1, row 4" }));
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
  });

  it("does not block a selection the build accepts, even with every WT row unticked", async () => {
    // A relative-scale file needs no WT: only the build knows that.
    refusalFor = () => null;
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    await reviewLoaded();
    fireEvent.click(screen.getByRole("checkbox", { name: "Use WT at block 1, row 4" }));
    await waitFor(() => expect(previewGcRows).toHaveBeenLastCalledWith(expect.objectContaining({ excluded_rows: [toExcludedRow(WT)] })));
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
  });

  it("does not send a saved untick the review no longer lists", async () => {
    const stale = { ...toExcludedRow(USED), row_index: 40 };
    saveBuildEvolveproToStorage(form({ excludedRows: [stale, toExcludedRow(USED_2)] }), PROJECT);
    renderPanel();
    await reviewLoaded();
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
    expect(previewGcRows).toHaveBeenLastCalledWith(expect.objectContaining({ excluded_rows: [toExcludedRow(USED_2)] }));
    fireEvent.click(screen.getByRole("button", BUILD_BUTTON));
    await waitFor(() => expect(buildEvolveproInput).toHaveBeenCalledTimes(1));
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ excluded_rows: [toExcludedRow(USED_2)] }),
    );
  });

  it("empties the unticked rows when an input the review reads changes, and keeps them on the same pick", async () => {
    saveBuildEvolveproToStorage(form({ excludedRows: [toExcludedRow(USED)] }), PROJECT);
    renderPanel();
    await reviewLoaded();

    vi.mocked(open).mockResolvedValueOnce(LAYOUT);
    fireEvent.click(screen.getByRole("button", { name: "Browse Plate layout xlsx (optional)" }));
    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(loadBuildEvolveproFromStorage(PROJECT).excludedRows).toEqual([toExcludedRow(USED)]));

    vi.mocked(open).mockResolvedValueOnce("/project/other_layout.xlsx");
    fireEvent.click(screen.getByRole("button", { name: "Browse Plate layout xlsx (optional)" }));
    await waitFor(() => expect(loadBuildEvolveproFromStorage(PROJECT).layoutXlsx).toBe("/project/other_layout.xlsx"));
    expect(loadBuildEvolveproFromStorage(PROJECT).excludedRows).toEqual([]);
  });

  it("shows the rows the build left out and the WT rows it used", async () => {
    saveBuildEvolveproToStorage(form(), PROJECT);
    renderPanel();
    await reviewLoaded();
    await waitFor(() => expect(screen.getByRole("button", BUILD_BUTTON)).toBeEnabled());
    fireEvent.click(screen.getByRole("button", BUILD_BUTTON));
    expect(await screen.findByText("Rows left out or flagged (1)")).toBeInTheDocument();
    expect(screen.getByText("WT rows used as the reference (1)")).toBeInTheDocument();
    expect(screen.getByText("left out by you")).toBeInTheDocument();
  });
});
