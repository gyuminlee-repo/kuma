/**
 * BuildEvolveproInputPanel: two-axis source selection and client-side gating.
 *
 * The panel must send exactly one axis A (primary screen) source and at most
 * one axis B (confirmation) source, mirroring the backend _axis_sources
 * validator rather than letting it reject the request. Paths belonging to a
 * source that is no longer selected must never leak into the params, and the
 * build button must stay blocked while a required companion file is missing.
 */

import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";

const mockSetBuildEvolveproCompletion = vi.hoisted(() => vi.fn());
const mockRegisterArtifacts = vi.hoisted(() => vi.fn());
const mockMkdir = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
  save: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-fs", () => ({
  mkdir: mockMkdir,
}));
vi.mock("@/lib/ipc-mame", () => ({
  buildEvolveproInput: vi.fn(),
}));
vi.mock("@/lib/openFolder", () => ({
  revealInOSFolder: vi.fn(),
}));
vi.mock("@/lib/workspace", () => ({
  registerArtifacts: mockRegisterArtifacts,
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
  createBuildEvolveproCompletion,
  loadBuildEvolveproFromStorage,
  seedBuildEvolveproForm,
  type BuildEvolveproFormState,
  type BuildEvolveproPrimarySource,
  type BuildEvolveproConfirmationSource,
} from "@/lib/mame/buildEvolveproFormStorage";
import type { BuildEvolveproInputResult } from "@/types/mame/build_evolvepro_input";
import { BuildEvolveproInputPanel } from "./BuildEvolveproInputPanel";

const mockBuild = vi.mocked(buildEvolveproInput);

function seed(partial: Partial<BuildEvolveproFormState>): void {
  const state: BuildEvolveproFormState = {
    ...BUILD_EVOLVEPRO_DEFAULT_STATE,
    ...partial,
  };
  localStorage.setItem(BUILD_EVOLVEPRO_STORAGE_KEY, JSON.stringify(state));
}

/** Writes a raw payload, for exercising the legacy single-toggle migration. */
function seedRaw(payload: Record<string, unknown>): void {
  localStorage.setItem(BUILD_EVOLVEPRO_STORAGE_KEY, JSON.stringify(payload));
}

const RESULT: BuildEvolveproInputResult = {
  output_path: "/out/ep.xlsx",
  mode: "rank",
  primary_source: "gc_sheet",
  confirmation_source: "numeric_index",
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
const OUTPUT = "/out/ep.xlsx";

/** Files each axis A source needs, and the params it is expected to send. */
const PRIMARY_SEED: Record<
  BuildEvolveproPrimarySource,
  Partial<BuildEvolveproFormState>
> = {
  rawReport: {
    layoutXlsx: "/in/layout.xlsx",
    round1ReportXlsx: "/in/round1_report.xlsx",
  },
  gcSheet: { layoutXlsx: "/in/layout.xlsx", gcDataXlsx: "/in/gc.xlsx" },
  prevEvolvepro: { round1EvolveproXlsx: "/in/round1_ep.xlsx" },
  numericReport: {
    round1RepBatchXlsx: "/in/round1_rep.xlsx",
    expectedMutationsXlsx: "/in/expected.xlsx",
  },
};

const PRIMARY_PARAMS: Record<BuildEvolveproPrimarySource, object> = {
  rawReport: {
    layout_xlsx: "/in/layout.xlsx",
    round1_report_xlsx: "/in/round1_report.xlsx",
    gc_export_xlsx: undefined,
  },
  gcSheet: { layout_xlsx: "/in/layout.xlsx", gc_data_xlsx: "/in/gc.xlsx" },
  prevEvolvepro: {
    round1_evolvepro_xlsx: "/in/round1_ep.xlsx",
    layout_xlsx: undefined,
  },
  // The design wins when both order sources are filled, so layout_xlsx is not
  // sent at all rather than sent alongside it.
  numericReport: {
    round1_rep_batch_xlsx: "/in/round1_rep.xlsx",
    expected_mutations_xlsx: "/in/expected.xlsx",
  },
};

/** Files each axis B source needs, and the params it is expected to send. */
const CONFIRM_SEED: Record<
  Exclude<BuildEvolveproConfirmationSource, "none">,
  Partial<BuildEvolveproFormState>
> = {
  variantLabels: { remeasureReportXlsx: "/in/remeasure.xlsx" },
  numericIndex: {
    repBatchXlsx: "/in/rep.xlsx",
    prevEvolveproXlsx: "/in/prev_ep.xlsx",
  },
  numericSubset: { remeasureRepBatchXlsx: "/in/remeasure_rep.xlsx" },
};

const CONFIRM_PARAMS: Record<
  Exclude<BuildEvolveproConfirmationSource, "none">,
  object
> = {
  variantLabels: { remeasure_report_xlsx: "/in/remeasure.xlsx" },
  numericIndex: {
    rep_batch_xlsx: "/in/rep.xlsx",
    prev_evolvepro_xlsx: "/in/prev_ep.xlsx",
  },
  numericSubset: { remeasure_rep_batch_xlsx: "/in/remeasure_rep.xlsx" },
};

const PRIMARY_SOURCES: BuildEvolveproPrimarySource[] = [
  "rawReport",
  "gcSheet",
  "prevEvolvepro",
  "numericReport",
];
const CONFIRM_SOURCES: Exclude<BuildEvolveproConfirmationSource, "none">[] = [
  "variantLabels",
  "numericSubset",
  "numericIndex",
];
// Every pair except numericSubset with a non-numeric primary. Those IDs number
// the above-WT subset of the numeric primary screen, so no other axis A source
// can produce the set they index into; the panel blocks that pair instead of
// submitting it.
const COMBINATIONS = PRIMARY_SOURCES.flatMap((primary) =>
  CONFIRM_SOURCES.filter(
    (confirmation) =>
      confirmation !== "numericSubset" || primary === "numericReport",
  ).map((confirmation) => ({ primary, confirmation })),
);

function helpButtonFor(labelText: string): HTMLElement {
  const label = screen.getByText(labelText, { selector: "label" });
  const wrapper = label.parentElement;
  if (!wrapper) {
    throw new Error(`Expected ${labelText} label to have a help wrapper`);
  }
  return within(wrapper).getByRole("button");
}

function deferredBuild() {
  let resolve!: (value: BuildEvolveproInputResult) => void;
  const promise = new Promise<BuildEvolveproInputResult>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mockBuild.mockResolvedValue(RESULT);
  mockRegisterArtifacts.mockResolvedValue(undefined);
  mockMkdir.mockResolvedValue(undefined);
});

describe("BuildEvolveproInputPanel axis toggles", () => {
  it("defaults to the GC sheet primary screen with no confirmation", () => {
    render(<BuildEvolveproInputPanel />);

    expect(
      screen.getByRole("radio", { name: "GC data sheet" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("radio", { name: "None (provisional)" }),
    ).toHaveAttribute("aria-checked", "true");

    const missing = screen.getByText(/Still needed/);
    expect(missing.textContent).toContain("Plate layout xlsx");
    expect(missing.textContent).toContain("GC data xlsx");
    expect(missing.textContent).toContain("Output EVOLVEpro xlsx");
    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
  });

  it("builds provisionally with no confirmation source selected", async () => {
    seed({ ...PRIMARY_SEED.gcSheet, outputXlsx: OUTPUT });
    render(<BuildEvolveproInputPanel />);

    expect(screen.queryByText(/Still needed/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      ...PRIMARY_PARAMS.gcSheet,
      verdict_xlsx: undefined,
      output_xlsx: OUTPUT,
    });
  });

  it("defaults the EVOLVEpro output into the active project activity folder and registers it", async () => {
    seed({ ...PRIMARY_SEED.gcSheet });
    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BuildEvolveproInputPanel />
      </ProjectProvider>,
    );

    await waitFor(() => {
      expect(screen.queryByText(/Still needed/)).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      ...PRIMARY_PARAMS.gcSheet,
      verdict_xlsx: undefined,
      output_xlsx: "/proj/activity/evolvepro_input.xlsx",
    });
    expect(mockMkdir).toHaveBeenCalledWith("/proj/activity", { recursive: true });
    await waitFor(() => {
      expect(mockRegisterArtifacts).toHaveBeenCalledWith([
        {
          app: "mame",
          step: "activity",
          type: "evolvepro_csv",
          absolutePath: RESULT.output_path,
        },
      ]);
    });
  });

  it.each(COMBINATIONS)(
    "submits the $primary primary screen with $confirmation confirmation",
    async ({ primary, confirmation }) => {
      seed({
        primarySource: primary,
        confirmationSource: confirmation,
        ...PRIMARY_SEED[primary],
        ...CONFIRM_SEED[confirmation],
        outputXlsx: OUTPUT,
      });
      render(<BuildEvolveproInputPanel />);

      expect(screen.queryByText(/Still needed/)).not.toBeInTheDocument();
      const button = screen.getByRole("button", { name: BUILD_LABEL });
      expect(button).toBeEnabled();

      fireEvent.click(button);

      await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
      expect(mockBuild).toHaveBeenCalledWith({
        ...PRIMARY_PARAMS[primary],
        ...CONFIRM_PARAMS[confirmation],
        verdict_xlsx: undefined,
        output_xlsx: OUTPUT,
      });
    },
  );

  it("sends a raw primary screen alongside a numeric-index confirmation", async () => {
    // The combination the single "Activity source" toggle could not express:
    // a raw well-labeled primary screen plus a rank-mapped confirmation.
    seed({
      primarySource: "rawReport",
      confirmationSource: "numericIndex",
      layoutXlsx: "/in/layout.xlsx",
      round1ReportXlsx: "/in/round1_report.xlsx",
      repBatchXlsx: "/in/rep.xlsx",
      prevEvolveproXlsx: "/in/prev_ep.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      layout_xlsx: "/in/layout.xlsx",
      round1_report_xlsx: "/in/round1_report.xlsx",
      gc_export_xlsx: undefined,
      rep_batch_xlsx: "/in/rep.xlsx",
      prev_evolvepro_xlsx: "/in/prev_ep.xlsx",
      verdict_xlsx: undefined,
      output_xlsx: OUTPUT,
    });
  });

  it("keeps a deselected source path out of the request", async () => {
    // prevEvolveproXlsx belongs to the numeric-index confirmation only. The
    // backend rejects it without rep_batch_xlsx, so a stale value must not ride
    // along after switching to the variant-labeled confirmation.
    seed({
      primarySource: "gcSheet",
      confirmationSource: "variantLabels",
      ...PRIMARY_SEED.gcSheet,
      remeasureReportXlsx: "/in/remeasure.xlsx",
      repBatchXlsx: "/in/rep.xlsx",
      prevEvolveproXlsx: "/in/prev_ep.xlsx",
      round1ReportXlsx: "/in/round1_report.xlsx",
      gcExportXlsx: "/out/gc.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    const sent = mockBuild.mock.calls[0][0];
    expect(sent.prev_evolvepro_xlsx).toBeUndefined();
    expect(sent.rep_batch_xlsx).toBeUndefined();
    expect(sent.round1_report_xlsx).toBeUndefined();
    expect(sent.gc_export_xlsx).toBeUndefined();
    expect(sent.gc_data_xlsx).toBe("/in/gc.xlsx");
  });

  it("blocks a numeric-subset confirmation paired with another primary", () => {
    // Its IDs number the above-WT subset of the numeric primary screen. Paired
    // with any other axis A source they would index a set never measured, so
    // the panel refuses rather than submitting.
    seed({
      primarySource: "gcSheet",
      confirmationSource: "numericSubset",
      ...PRIMARY_SEED.gcSheet,
      ...CONFIRM_SEED.numericSubset,
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    expect(screen.getByText(/Still needed/).textContent).toContain(
      "Primary screen (numeric IDs)",
    );
    expect(mockBuild).not.toHaveBeenCalled();
  });

  it("blocks a numeric primary screen until an order source is chosen", () => {
    // Bare numeric sample names carry no variant information, so either the
    // KURO design or the hand-written layout has to be present.
    seed({
      primarySource: "numericReport",
      confirmationSource: "none",
      round1RepBatchXlsx: "/in/round1_rep.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    expect(screen.getByText(/Still needed/).textContent).toContain(
      "KURO design",
    );
    expect(mockBuild).not.toHaveBeenCalled();
  });

  it("accepts the hand-written layout as the numeric order source", () => {
    seed({
      primarySource: "numericReport",
      confirmationSource: "none",
      round1RepBatchXlsx: "/in/round1_rep.xlsx",
      layoutXlsx: "/in/layout.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeEnabled();
  });

  it("blocks a numeric-index confirmation until the rank source is chosen", () => {
    seed({
      primarySource: "gcSheet",
      confirmationSource: "numericIndex",
      ...PRIMARY_SEED.gcSheet,
      repBatchXlsx: "/in/rep.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    expect(screen.getByText(/Still needed/).textContent).toContain(
      "Rank source EVOLVEpro input xlsx",
    );
    expect(mockBuild).not.toHaveBeenCalled();
  });

  it("blocks a raw primary screen until the plate layout is chosen", () => {
    seed({
      primarySource: "rawReport",
      confirmationSource: "variantLabels",
      round1ReportXlsx: "/in/round1_report.xlsx",
      ...CONFIRM_SEED.variantLabels,
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    expect(screen.getByText(/Still needed/).textContent).toContain(
      "Plate layout xlsx",
    );
    expect(mockBuild).not.toHaveBeenCalled();
  });

  it("blocks a variant-labeled confirmation until its report is chosen", () => {
    seed({
      primarySource: "prevEvolvepro",
      confirmationSource: "variantLabels",
      ...PRIMARY_SEED.prevEvolvepro,
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
    expect(screen.getByText(/Still needed/).textContent).toContain(
      "Confirmation report xlsx (variant-labeled)",
    );
  });

  it("swaps the visible pickers when either axis changes", () => {
    render(<BuildEvolveproInputPanel />);

    expect(screen.getByLabelText("GC data xlsx")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Confirmation report xlsx (variant-labeled)"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Raw GC-FID report" }));

    expect(screen.queryByLabelText("GC data xlsx")).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Primary screen report xlsx (raw GC-FID)"),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("radio", { name: "Numeric-index report" }),
    );

    expect(
      screen.getByLabelText("Rank source EVOLVEpro input xlsx"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Agilent confirmation report xlsx"),
    ).toBeInTheDocument();
  });

  it("keeps the NGS verdict picker available on every axis pair", () => {
    render(<BuildEvolveproInputPanel />);
    expect(screen.getByLabelText(/NGS verdict xlsx/)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("radio", { name: "Previous EVOLVEpro input" }),
    );
    expect(screen.getByLabelText(/NGS verdict xlsx/)).toBeInTheDocument();
  });

  it("sends the NGS verdict path on a previous-EVOLVEpro primary screen", async () => {
    seed({
      primarySource: "prevEvolvepro",
      confirmationSource: "variantLabels",
      ...PRIMARY_SEED.prevEvolvepro,
      ...CONFIRM_SEED.variantLabels,
      verdictXlsx: "/in/verdict.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      round1_evolvepro_xlsx: "/in/round1_ep.xlsx",
      layout_xlsx: undefined,
      remeasure_report_xlsx: "/in/remeasure.xlsx",
      verdict_xlsx: "/in/verdict.xlsx",
      output_xlsx: OUTPUT,
    });
  });

  it("offers the relative-activity export only on the raw primary screen", async () => {
    seed({
      primarySource: "rawReport",
      confirmationSource: "variantLabels",
      ...PRIMARY_SEED.rawReport,
      ...CONFIRM_SEED.variantLabels,
      gcExportXlsx: "/out/gc.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(
      screen.getByLabelText(/Relative activity export xlsx/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockBuild).toHaveBeenCalledWith({
      layout_xlsx: "/in/layout.xlsx",
      round1_report_xlsx: "/in/round1_report.xlsx",
      gc_export_xlsx: "/out/gc.xlsx",
      remeasure_report_xlsx: "/in/remeasure.xlsx",
      verdict_xlsx: undefined,
      output_xlsx: OUTPUT,
    });

    fireEvent.click(screen.getByRole("radio", { name: "GC data sheet" }));
    expect(
      screen.queryByLabelText(/Relative activity export xlsx/),
    ).not.toBeInTheDocument();
  });

  it("offers inline help toggles for both axis toggles and the visible files", () => {
    render(<BuildEvolveproInputPanel />);

    // primary toggle, layout, GC data, confirmation toggle, verdict, output.
    expect(screen.getAllByRole("button", { name: "Show help" })).toHaveLength(6);

    const primaryHelp = helpButtonFor("Primary screen source");
    fireEvent.click(primaryHelp);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Pre-normalised relative activity per well",
    );
    fireEvent.click(primaryHelp);

    const confirmationHelp = helpButtonFor("Confirmation source");
    fireEvent.click(confirmationHelp);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "No confirmation input",
    );
    fireEvent.click(confirmationHelp);

    fireEvent.click(
      screen.getByRole("radio", { name: "Numeric-index report" }),
    );
    // The two numeric-index files add their own help toggles.
    expect(screen.getAllByRole("button", { name: "Show help" })).toHaveLength(8);
    fireEvent.click(helpButtonFor("Confirmation source"));
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "sample names are numeric base IDs",
    );
  });

  it("focuses the matching field when a missing input is clicked", () => {
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Plate layout xlsx" }));

    expect(screen.getByLabelText("Plate layout xlsx")).toHaveFocus();
  });

  it("can clear restored EVOLVEpro input paths without clearing the whole Mame project", () => {
    seed({ ...PRIMARY_SEED.gcSheet, outputXlsx: OUTPUT });

    render(<BuildEvolveproInputPanel />);

    expect(screen.getByText("layout.xlsx")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Clear restored EVOLVEpro inputs" }),
    );

    expect(screen.queryByText("layout.xlsx")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeDisabled();
  });

  it("records the completion signature of the submitted form", async () => {
    seed({ ...PRIMARY_SEED.gcSheet, outputXlsx: OUTPUT });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));
    expect(mockSetBuildEvolveproCompletion).toHaveBeenLastCalledWith(
      createBuildEvolveproCompletion(
        {
          ...BUILD_EVOLVEPRO_DEFAULT_STATE,
          ...PRIMARY_SEED.gcSheet,
          outputXlsx: OUTPUT,
        },
        OUTPUT,
      ),
    );
  });

  it("ignores a successful build that resolves after the form changed", async () => {
    const pending = deferredBuild();
    mockBuild.mockReturnValueOnce(pending.promise);
    seed({ ...PRIMARY_SEED.gcSheet, outputXlsx: OUTPUT });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));
    await waitFor(() => expect(mockBuild).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole("button", { name: "Clear restored EVOLVEpro inputs" }),
    );
    pending.resolve(RESULT);

    await waitFor(() =>
      expect(mockSetBuildEvolveproCompletion).toHaveBeenLastCalledWith(null),
    );
    expect(
      mockSetBuildEvolveproCompletion.mock.calls.some(
        ([completion]) => completion !== null,
      ),
    ).toBe(false);
  });
});

describe("BuildEvolveproInputPanel result summary", () => {
  it("reports the axis pair and marks a build without confirmation provisional", async () => {
    mockBuild.mockResolvedValue({
      ...RESULT,
      primary_source: "prev_evolvepro",
      confirmation_source: "none",
      confidence: undefined,
    });
    seed({
      primarySource: "prevEvolvepro",
      ...PRIMARY_SEED.prevEvolvepro,
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() =>
      expect(screen.getByText(/Built from/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Built from/).textContent).toContain(
      "Previous EVOLVEpro input",
    );
    expect(screen.getByText(/Built from/).textContent).toContain(
      "None (provisional)",
    );
    // No "confidence" field is returned on this axis pair, so the badge has to
    // come from confirmation_source or it would silently disappear.
    expect(
      screen.getByText("Provisional (no confirmation input)"),
    ).toBeInTheDocument();
  });

  it("marks a build with a confirmation source confirmed", async () => {
    seed({
      confirmationSource: "numericIndex",
      ...PRIMARY_SEED.gcSheet,
      ...CONFIRM_SEED.numericIndex,
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    fireEvent.click(screen.getByRole("button", { name: BUILD_LABEL }));

    await waitFor(() =>
      expect(screen.getByText(/Built from/)).toBeInTheDocument(),
    );
    expect(
      screen.getByText("Confirmed (confirmation replicates merged)"),
    ).toBeInTheDocument();
  });
});

describe("BuildEvolveproInputPanel legacy storage migration", () => {
  it("maps a legacy rank payload without confirmation files onto GC sheet + none", () => {
    seedRaw({
      sourceMode: "rank",
      round1Source: "prev",
      layoutXlsx: "/in/layout.xlsx",
      gcDataXlsx: "/in/gc.xlsx",
      outputXlsx: OUTPUT,
    });

    const state = loadBuildEvolveproFromStorage();

    expect(state.primarySource).toBe("gcSheet");
    expect(state.confirmationSource).toBe("none");
    expect(state.gcDataXlsx).toBe("/in/gc.xlsx");
  });

  it("maps a legacy rank payload with the confirmation pair onto numeric index", () => {
    seedRaw({
      sourceMode: "rank",
      layoutXlsx: "/in/layout.xlsx",
      gcDataXlsx: "/in/gc.xlsx",
      repBatchXlsx: "/in/rep.xlsx",
      prevEvolveproXlsx: "/in/prev_ep.xlsx",
      outputXlsx: OUTPUT,
    });

    const state = loadBuildEvolveproFromStorage();

    expect(state.primarySource).toBe("gcSheet");
    expect(state.confirmationSource).toBe("numericIndex");
  });

  it("maps the legacy reports payloads onto their primary screen source", () => {
    seedRaw({ sourceMode: "reports", round1Source: "raw" });
    expect(loadBuildEvolveproFromStorage()).toMatchObject({
      primarySource: "rawReport",
      confirmationSource: "variantLabels",
    });

    seedRaw({ sourceMode: "reports", round1Source: "prev" });
    expect(loadBuildEvolveproFromStorage()).toMatchObject({
      primarySource: "prevEvolvepro",
      confirmationSource: "variantLabels",
    });
  });

  it("renders a migrated legacy payload without losing its paths", () => {
    seedRaw({
      sourceMode: "reports",
      round1Source: "raw",
      layoutXlsx: "/in/layout.xlsx",
      round1ReportXlsx: "/in/round1_report.xlsx",
      remeasureReportXlsx: "/in/remeasure.xlsx",
      outputXlsx: OUTPUT,
    });
    render(<BuildEvolveproInputPanel />);

    expect(
      screen.getByRole("radio", { name: "Raw GC-FID report" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByRole("radio", { name: "Variant-labeled report" }),
    ).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("button", { name: BUILD_LABEL })).toBeEnabled();
  });
});

describe("BuildEvolveproInputPanel sample data seeding", () => {
  const SAMPLE = {
    layoutXlsx: "/sample/layout.xlsx",
    gcDataXlsx: "/sample/gc.xlsx",
    round1ReportXlsx: "/sample/raw-round1.xlsx",
    remeasureReportXlsx: "/sample/remeasure.xlsx",
    repBatchXlsx: "/sample/rep.xlsx",
    prevEvolveproXlsx: "/sample/prev_ep.xlsx",
  };

  it("selects the raw GC-FID primary screen and numeric-index confirmation the seeded files belong to", () => {
    // Without this the seeded rank files land behind an unselected axis and the
    // sample data silently renders as an empty form.
    seedBuildEvolveproForm(SAMPLE);

    const state = loadBuildEvolveproFromStorage();

    expect(state.primarySource).toBe("rawReport");
    expect(state.confirmationSource).toBe("numericIndex");
    expect(state.round1ReportXlsx).toBe("/sample/raw-round1.xlsx");
    expect(state.remeasureReportXlsx).toBe("/sample/remeasure.xlsx");
    expect(state.repBatchXlsx).toBe("/sample/rep.xlsx");
    expect(state.prevEvolveproXlsx).toBe("/sample/prev_ep.xlsx");
  });

  it("leaves a confirmation source the user already picked alone", () => {
    seed({ confirmationSource: "variantLabels" });

    seedBuildEvolveproForm(SAMPLE);

    expect(loadBuildEvolveproFromStorage().confirmationSource).toBe(
      "variantLabels",
    );
  });

  it("does not select a confirmation source when only one rank file is seeded", () => {
    seedBuildEvolveproForm({
      layoutXlsx: SAMPLE.layoutXlsx,
      round1ReportXlsx: SAMPLE.round1ReportXlsx,
      repBatchXlsx: SAMPLE.repBatchXlsx,
    });

    expect(loadBuildEvolveproFromStorage().confirmationSource).toBe("none");
  });
});
