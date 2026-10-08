import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRoundStore } from "@/store/round/roundSlice";
import { ProjectProvider } from "@/state/projectContext";

const mockSetBuildEvolveproCompletion = vi.hoisted(() => vi.fn());
const mockMkdir = vi.hoisted(() => vi.fn());
// Mutable so a test can bump `buildEvolveproSeedEpoch` mid-test (mirroring
// `loadSampleData`'s post-seed bump) and observe the panel re-read storage on
// its next render, the same way it observes `resetEpoch`.
const mockMameState = vi.hoisted(() => ({
  resetEpoch: 0,
  buildEvolveproSeedEpoch: 0,
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: mockMkdir }));
vi.mock("@/lib/ipc-mame", () => ({
  buildEvolveproInput: vi.fn(),
  detectMeasurementSource: vi.fn(),
}));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("@/lib/workspace", () => ({ registerArtifacts: vi.fn().mockResolvedValue(undefined) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/store/mame/mameAppStore", () => ({
  useMameAppStore: (selector: (state: {
    resetEpoch: number;
    buildEvolveproSeedEpoch: number;
    setBuildEvolveproCompletion: typeof mockSetBuildEvolveproCompletion;
  }) => unknown) =>
    selector({ ...mockMameState, setBuildEvolveproCompletion: mockSetBuildEvolveproCompletion }),
}));

import { open } from "@tauri-apps/plugin-dialog";
import { buildEvolveproInput, detectMeasurementSource } from "@/lib/ipc-mame";
import type { DetectMeasurementSourceResult } from "@/types/mame/detect_measurement_source";
import {
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  BUILD_EVOLVEPRO_STORAGE_KEY,
  createBuildEvolveproCompletion,
  hasCompletedBuildEvolveproOutput,
  loadBuildEvolveproFromStorage,
  saveBuildEvolveproToStorage,
  type BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";
import type { BuildEvolveproInputResult } from "@/types/mame/build_evolvepro_input";
import {
  getFormatPreview,
  type FormatPreviewId,
} from "@/data/mameFormatPreviews";
import { BuildEvolveproInputPanel } from "./BuildEvolveproInputPanel";

const PROJECT = "/project";
const LABEL_SWAP_MESSAGE =
  "Label swap detected; export blocked. Review the layout and verdict labels " +
  "or set allow_label_mismatch=True after review.";
const LAYOUT_LABEL = "Plate layout xlsx (optional)";
const RESULT: BuildEvolveproInputResult = {
  output_path: "/project/activity/evolvepro_input.xlsx",
  n_variants: 3,
  n_authoritative: 3,
  n_fallback_only: 0,
  warnings: [],
  mismatched: [],
  n_ngs_excluded: 0,
  ngs_excluded: [],
  gc_export_path: "",
  label_audit: null,
  manifest_path: "/project/activity/evolvepro_input.xlsx.manifest.json",
  primary_format: "activity_path",
  input_count: 3,
  evaluable_count: 3,
  exclusion_reason_counts: {},
  normalization_sources: ["activity_path:relative_to_wt"],
  evidence_hash: "sha256:evidence",
  artifact_hashes: { "/project/activity/evolvepro_input.xlsx": "sha256:output" },
  wt_values: [1.02, 0.97, 1.04, 0.99],
  variant_replicates: { "5F": [1.48, 1.52], "10L": [0.61], "22A": [2.05, 1.98, 2.02] },
};

const readyForm = (overrides: Partial<BuildEvolveproFormState> = {}): BuildEvolveproFormState => ({
  ...BUILD_EVOLVEPRO_DEFAULT_STATE,
  activityPath: "/project/activity/activity.csv",
  verdictXlsx: "/project/ngs/verdict.xlsx",
  outputXlsx: RESULT.output_path,
  ...overrides,
});
const WELL_LABELED_FORMS: Array<[string, BuildEvolveproFormState, Record<string, string>]> = [
  [
    "GC sheet",
    readyForm({
      primarySource: "gcSheet",
      layoutXlsx: "/project/layout.xlsx",
      gcDataXlsx: "/project/gc.xlsx",
    }),
    { gc_data_xlsx: "/project/gc.xlsx", layout_xlsx: "/project/layout.xlsx" },
  ],
  [
    "raw report",
    readyForm({
      primarySource: "rawReport",
      layoutXlsx: "/project/layout.xlsx",
      round1ReportXlsx: "/project/report.xlsx",
    }),
    { round1_report_xlsx: "/project/report.xlsx", layout_xlsx: "/project/layout.xlsx" },
  ],
];


function seed(form: BuildEvolveproFormState): void {
  saveBuildEvolveproToStorage(form, PROJECT);
}

function renderPanel() {
  return render(
    <ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}>
      <BuildEvolveproInputPanel />
    </ProjectProvider>,
  );
}

async function build(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: "Build EVOLVEpro input" }));
  await waitFor(() => expect(buildEvolveproInput).toHaveBeenCalledTimes(1));
}

const MEASUREMENT_LABEL = "Experiment data file";
const ADDITIONAL_LABEL = "Additional experiment data file (optional)";
const BROWSE_MEASUREMENT = `Browse ${MEASUREMENT_LABEL}`;
const CHOSEN = "/project/activity/chosen.xlsx";

function detection(
  candidates: DetectMeasurementSourceResult["candidates"],
  reason = "",
  path = CHOSEN,
): DetectMeasurementSourceResult {
  return {
    path,
    candidates,
    ambiguous: candidates.length > 1,
    evidence: {},
    reason,
  };
}

/** Choose a measurement file and let the detection round-trip settle. */
async function chooseMeasurement(path = CHOSEN): Promise<void> {
  vi.mocked(open).mockResolvedValueOnce(path);
  fireEvent.click(screen.getByRole("button", { name: BROWSE_MEASUREMENT }));
  await waitFor(() =>
    expect(detectMeasurementSource).toHaveBeenCalledWith({ measurement_path: path }),
  );
}

beforeEach(() => {
  localStorage.clear();
  useRoundStore.setState({ rounds: [], active_round_id: null });
  vi.clearAllMocks();
  mockMkdir.mockResolvedValue(undefined);
  vi.mocked(buildEvolveproInput).mockResolvedValue(RESULT);
  vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["longFormat"]));
  mockMameState.resetEpoch = 0;
  mockMameState.buildEvolveproSeedEpoch = 0;
});

describe("BuildEvolveproInputPanel unified Activity-step inputs", () => {
  it("builds long-format activity with its explicit scale and shared verdict", async () => {
    seed(readyForm({ activityScale: "relative_to_wt" }));
    renderPanel();

    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith({
      activity_path: "/project/activity/activity.csv",
      activity_scale: "relative_to_wt",
      allow_label_mismatch: false,
      remeasure_report_xlsx: undefined,
      verdict_xlsx: "/project/ngs/verdict.xlsx",
      output_xlsx: RESULT.output_path,
      mismatch_threshold: 0.1,
    });
  });

  it("offers the label-mismatch acknowledgement only after the build is refused for it", async () => {
    vi.mocked(buildEvolveproInput).mockRejectedValueOnce(new Error(LABEL_SWAP_MESSAGE));
    seed(readyForm());
    renderPanel();

    // Nothing to acknowledge before a refusal.
    expect(
      screen.queryByRole("checkbox", { name: "Allow reviewed label mismatch" }),
    ).not.toBeInTheDocument();

    await build();
    expect(buildEvolveproInput).toHaveBeenLastCalledWith(
      expect.objectContaining({ allow_label_mismatch: false }),
    );

    const checkbox = await screen.findByRole("checkbox", {
      name: "Allow reviewed label mismatch",
    });
    expect(screen.getByRole("alert")).toContainElement(checkbox);

    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "Build EVOLVEpro input" }));
    await waitFor(() => expect(buildEvolveproInput).toHaveBeenCalledTimes(2));

    expect(buildEvolveproInput).toHaveBeenLastCalledWith(
      expect.objectContaining({ allow_label_mismatch: true }),
    );
  });

  it("keeps the acknowledgement off an ordinary build failure", async () => {
    vi.mocked(buildEvolveproInput).mockRejectedValueOnce(
      new Error("Verdict sheet has no PASS rows"),
    );
    seed(readyForm());
    renderPanel();

    await build();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: "Allow reviewed label mismatch" }),
    ).not.toBeInTheDocument();
  });

  it("hides the mismatch threshold while no confirmation source can populate it", async () => {
    seed(readyForm());
    renderPanel();

    expect(screen.queryByLabelText("Mismatch threshold")).not.toBeInTheDocument();

    // The value is still sent, so the backend keeps behaving identically.
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ mismatch_threshold: 0.1 }),
    );
  });

  it("shows the mismatch threshold once a confirmation source is selected", () => {
    seed(readyForm({
      confirmationSource: "variantLabels",
      remeasureReportXlsx: "/project/remeasure.xlsx",
    }));
    renderPanel();

    expect(screen.getByLabelText("Mismatch threshold")).toBeInTheDocument();
  });

  it("summarises an auto-filled verdict and output until the operator asks to change them", () => {
    seed(readyForm());
    renderPanel();

    expect(screen.queryByLabelText("NGS verdict xlsx")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Output EVOLVEpro xlsx" })).not.toBeInTheDocument();
    expect(screen.getByText("verdict.xlsx")).toBeInTheDocument();
    expect(screen.getByText("evolvepro_input.xlsx")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Change: NGS verdict xlsx" }));
    expect(screen.getByLabelText("NGS verdict xlsx")).toHaveValue("verdict.xlsx");
    // Only the field that was asked for opens.
    expect(screen.queryByRole("textbox", { name: "Output EVOLVEpro xlsx" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Change: Output EVOLVEpro xlsx" }));
    expect(screen.getByRole("textbox", { name: "Output EVOLVEpro xlsx" })).toHaveValue(
      "evolvepro_input.xlsx",
    );
  });

  it("shows the picker outright when the verdict or output is still empty", () => {
    seed(readyForm({ verdictXlsx: "", outputXlsx: "" }));
    renderPanel();

    expect(screen.getByLabelText("NGS verdict xlsx")).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "Output EVOLVEpro xlsx" })).toHaveValue("");
    // Still gated on those two inputs.
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
  });

  it("folds the optional plate layout away, and unfolds it when one is selected", () => {
    seed(readyForm());
    const { unmount } = renderPanel();

    expect(screen.getByLabelText(LAYOUT_LABEL)).not.toBeVisible();
    unmount();

    seed(readyForm({ layoutXlsx: "/project/layout.xlsx" }));
    renderPanel();

    expect(screen.getByLabelText(LAYOUT_LABEL)).toBeVisible();
    expect(screen.getByLabelText(LAYOUT_LABEL)).toHaveValue("layout.xlsx");
  });

  it.each(WELL_LABELED_FORMS)("builds %s with a layout and one selected primary source", async (_name, form, primary) => {
    seed(form);
    renderPanel();

    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith({
      ...primary,
      allow_label_mismatch: false,
      remeasure_report_xlsx: undefined,
      verdict_xlsx: "/project/ngs/verdict.xlsx",
      output_xlsx: RESULT.output_path,
      mismatch_threshold: 0.1,
    });
  });

  it.each([
    ["GC sheet", "gcSheet", "gcDataXlsx", "gc_data_xlsx", "/project/gc.xlsx"],
    ["raw report", "rawReport", "round1ReportXlsx", "round1_report_xlsx", "/project/report.xlsx"],
  ] as const)(
    "builds %s without a layout, leaving the well mapping to the verdict sheet",
    async (_name, primarySource, formKey, paramKey, path) => {
      seed(readyForm({ primarySource, [formKey]: path, layoutXlsx: "" }));
      renderPanel();

      await build();

      expect(buildEvolveproInput).toHaveBeenCalledWith({
        [paramKey]: path,
        layout_xlsx: undefined,
        allow_label_mismatch: false,
        remeasure_report_xlsx: undefined,
        verdict_xlsx: "/project/ngs/verdict.xlsx",
        output_xlsx: RESULT.output_path,
        mismatch_threshold: 0.1,
      });
    },
  );

  it("builds a numeric-ID screen against the designed variant list", async () => {
    seed(readyForm({
      primarySource: "numericReport",
      numericReportXlsx: "/project/screen.xlsx",
      expectedXlsx: "/project/expected.xlsx",
      layoutXlsx: "",
    }));
    renderPanel();

    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith({
      numeric_report_xlsx: "/project/screen.xlsx",
      layout_xlsx: undefined,
      allow_label_mismatch: false,
      expected_xlsx: "/project/expected.xlsx",
      remeasure_report_xlsx: undefined,
      remeasure_numeric_xlsx: undefined,
      verdict_xlsx: "/project/ngs/verdict.xlsx",
      output_xlsx: RESULT.output_path,
      mismatch_threshold: 0.1,
    });
  });

  it("sends the replicated confirmation for numeric-ID confirmation", async () => {
    seed(readyForm({
      confirmationSource: "numericIds",
      remeasureNumericXlsx: "/project/confirm.xlsx",
      expectedXlsx: "/project/expected.xlsx",
      layoutXlsx: "",
    }));
    renderPanel();

    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      allow_label_mismatch: false,
      remeasure_numeric_xlsx: "/project/confirm.xlsx",
      remeasure_report_xlsx: undefined,
      expected_xlsx: "/project/expected.xlsx",
    }));
  });

  it.each([
    ["neither order source", { expectedXlsx: "", layoutXlsx: "" }],
    ["both order sources", { expectedXlsx: "/project/expected.xlsx", layoutXlsx: "/project/layout.xlsx" }],
  ])("blocks a numeric-ID build with %s", (_name, overrides) => {
    seed(readyForm({
      primarySource: "numericReport",
      numericReportXlsx: "/project/screen.xlsx",
      ...overrides,
    }));
    renderPanel();

    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(buildEvolveproInput).not.toHaveBeenCalled();
  });

  it("sends a confirmation report only for variant-labeled confirmation", async () => {
    seed(readyForm({ confirmationSource: "variantLabels", remeasureReportXlsx: "/project/remeasure.xlsx" }));
    renderPanel();

    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      allow_label_mismatch: false,
      remeasure_report_xlsx: "/project/remeasure.xlsx",
    }));
  });

  it("requires the verdict before any source can build", () => {
    seed(readyForm({ verdictXlsx: "" }));
    renderPanel();

    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(buildEvolveproInput).not.toHaveBeenCalled();
  });

  it("shows conversion guidance and blocks a removed saved selection", () => {
    localStorage.setItem(BUILD_EVOLVEPRO_STORAGE_KEY, JSON.stringify({
      primarySource: "legacy-primary",
      confirmationSource: "legacy-confirmation",
      outputXlsx: "/project/activity/evolvepro_input.xlsx",
    }));
    renderPanel();

    expect(screen.getByText(/no longer supported/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(buildEvolveproInput).not.toHaveBeenCalled();
  });
  it("invalidates completion signatures when an input or verdict changes", () => {
    const form = readyForm();
    const completion = createBuildEvolveproCompletion(form, form.outputXlsx);

    expect(hasCompletedBuildEvolveproOutput(
      { ...form, activityPath: "/project/activity/revised.csv" },
      completion,
    )).toBe(false);
    expect(hasCompletedBuildEvolveproOutput(
      { ...form, verdictXlsx: "/project/ngs/revised-verdict.xlsx" },
      completion,
    )).toBe(false);
  });
});

describe("BuildEvolveproInputPanel persistence", () => {
  it("keeps versioned form state project-scoped", () => {
    const form = readyForm({
      activityPath: "/project-a/activity/activity.csv",
      verdictXlsx: "/project-a/ngs/verdict.xlsx",
      outputXlsx: "/project-a/activity/evolvepro_input.xlsx",
    });
    saveBuildEvolveproToStorage(form, "/project-a");

    expect(loadBuildEvolveproFromStorage("/project-a")).toMatchObject(form);
    expect(loadBuildEvolveproFromStorage("/project-b")).toEqual(BUILD_EVOLVEPRO_DEFAULT_STATE);

    const scopedKey = Object.keys(localStorage).find((key) =>
      key.startsWith(`${BUILD_EVOLVEPRO_STORAGE_KEY}:v2:`),
    );
    expect(scopedKey).toBeDefined();
    expect(localStorage.getItem(scopedKey!)).toContain('"@project/activity/activity.csv"');
  });

  it("round-trips the mismatch threshold instead of reverting to the backend default", () => {
    const form = readyForm({ mismatchThreshold: 0.27 });
    saveBuildEvolveproToStorage(form, PROJECT);

    expect(loadBuildEvolveproFromStorage(PROJECT).mismatchThreshold).toBe(0.27);
  });

  it("does not silently consume ambiguous external legacy state", () => {
    localStorage.setItem(BUILD_EVOLVEPRO_STORAGE_KEY, JSON.stringify({
      activityPath: "/external/activity.csv",
      verdictXlsx: "/external/verdict.xlsx",
      outputXlsx: "/external/output.xlsx",
    }));

    expect(loadBuildEvolveproFromStorage(PROJECT)).toEqual({
      ...BUILD_EVOLVEPRO_DEFAULT_STATE,
      migrationNotice: true,
    });
  });
});

describe("BuildEvolveproInputPanel sample-data seed reload (defect 2 regression)", () => {
  // loadSampleData only writes to localStorage (seedBuildEvolveproForm); it
  // has no way to reach an already-mounted panel's React state directly. The
  // panel must notice via `buildEvolveproSeedEpoch` and re-read storage,
  // otherwise it keeps showing whatever it had at mount (here: nothing).
  it("re-reads storage once loadSampleData bumps buildEvolveproSeedEpoch", () => {
    const { rerender } = render(
      <ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}>
        <BuildEvolveproInputPanel />
      </ProjectProvider>,
    );

    // Mounted before any sample data existed: the measurement field is empty.
    expect(screen.getByLabelText(MEASUREMENT_LABEL)).toHaveValue("");

    // loadSampleData's seedBuildEvolveproForm writes straight to storage
    // without touching the panel's React state.
    saveBuildEvolveproToStorage(
      readyForm({ activityPath: "/project/samples/mame/14_mame_activity_long_raw.csv" }),
      PROJECT,
    );
    mockMameState.buildEvolveproSeedEpoch = 1;
    rerender(
      <ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}>
        <BuildEvolveproInputPanel />
      </ProjectProvider>,
    );

    // The seeded file arrives as a summary row, not a picker: it is already
    // chosen, and its format came from storage rather than from a detection.
    expect(screen.getByText("14_mame_activity_long_raw.csv")).toBeInTheDocument();
    expect(screen.getByText("Format: Generic long-format")).toBeInTheDocument();
  });

  it("does nothing on mount, before the epoch has ever bumped (epoch 0 is not a seed)", () => {
    saveBuildEvolveproToStorage(readyForm(), PROJECT);
    renderPanel();

    // The mount-time load (useState initializer) already picked this up;
    // asserting it here pins down that the epoch-0 guard does not clear it.
    expect(screen.getByText("activity.csv")).toBeInTheDocument();
  });
});

describe("BuildEvolveproInputPanel measurement format detection", () => {
  // The file is chosen first and its format is read from it. The detector is
  // asked once per selection and its answer is a LIST: one candidate is
  // applied, two are put to the operator, none falls back to the manual
  // choice. Nothing it says may stop the operator from proceeding.

  it("reads nothing on mount: a restored path was never sent to the detector", () => {
    seed(readyForm());
    renderPanel();

    expect(detectMeasurementSource).not.toHaveBeenCalled();
    // Reported as the stored format, not as something this panel detected.
    expect(screen.getByText("Format: Generic long-format")).toBeInTheDocument();
    expect(screen.queryByText(/^Detected:/)).not.toBeInTheDocument();
  });

  it("offers one file picker before any format has been chosen", () => {
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    expect(screen.getByLabelText(MEASUREMENT_LABEL)).toHaveValue("");
    // No four-way choice up front: the format comes from the file.
    for (const format of [
      "Generic long-format",
      "GC data sheet",
      "Raw Agilent report",
      "Numeric-ID Agilent report",
    ]) {
      expect(screen.queryByRole("radio", { name: format })).not.toBeInTheDocument();
    }
  });

  it("applies the single candidate a file reads as", async () => {
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["rawReport"]));
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    await chooseMeasurement();

    expect(await screen.findByText("Detected: Raw Agilent report")).toBeInTheDocument();
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ round1_report_xlsx: CHOSEN, layout_xlsx: undefined }),
    );
  });

  it.each([
    ["GC data sheet", "gc_data_xlsx"],
    ["Generic long-format", "activity_path"],
  ] as const)(
    "puts the GC/long-format pair to the operator, and files the chosen side (%s)",
    async (choice, paramKey) => {
      vi.mocked(detectMeasurementSource).mockResolvedValue(
        detection(["gcSheet", "longFormat"]),
      );
      seed(readyForm({ activityPath: "" }));
      renderPanel();

      await chooseMeasurement();

      expect(
        await screen.findByText(/reads as two formats/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/already relative to the wild type/i),
      ).toBeInTheDocument();
      // Only the two candidates are offered, never the whole four.
      expect(
        screen.queryByRole("radio", { name: "Raw Agilent report" }),
      ).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole("radio", { name: choice }));
      await build();

      expect(buildEvolveproInput).toHaveBeenCalledWith(
        expect.objectContaining({ [paramKey]: CHOSEN }),
      );
    },
  );

  it("puts the numeric pair to the operator and files it as the primary screen", async () => {
    vi.mocked(detectMeasurementSource).mockResolvedValue(
      detection(["numericReport", "confirmationNumericIds"]),
    );
    seed(readyForm({ activityPath: "", expectedXlsx: "/project/expected.xlsx" }));
    renderPanel();

    await chooseMeasurement();

    expect(
      await screen.findByText(/first measurement of the round/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Numeric-ID Agilent report" }));
    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({
        numeric_report_xlsx: CHOSEN,
        expected_xlsx: "/project/expected.xlsx",
      }),
    );
  });

  it("files the same numeric file in the confirmation slot when that side is chosen", async () => {
    vi.mocked(detectMeasurementSource).mockResolvedValue(
      detection(["numericReport", "confirmationNumericIds"]),
    );
    seed(readyForm({ expectedXlsx: "/project/expected.xlsx" }));
    renderPanel();

    // Change reopens the picker, so a second file can be chosen.
    fireEvent.click(screen.getByRole("button", { name: `Change: ${MEASUREMENT_LABEL}` }));
    await chooseMeasurement();

    // Scoped: the confirmation-source group carries the same option name, and
    // the point here is the choice offered for THIS file.
    const pair = await screen.findByRole("radiogroup", { name: "Measurement format" });
    fireEvent.click(
      within(pair).getByRole("radio", { name: "Numeric-ID replicate report" }),
    );

    // The confirmation slot took it; the primary measurement is untouched.
    expect(
      screen.getByRole("textbox", { name: ADDITIONAL_LABEL }),
    ).toHaveValue("chosen.xlsx");
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({
        remeasure_numeric_xlsx: CHOSEN,
        activity_path: "/project/activity/activity.csv",
      }),
    );
  });

  it("names a confirmation-only file as such and offers the slot it belongs in", async () => {
    vi.mocked(detectMeasurementSource).mockResolvedValue(
      detection(["confirmationVariantLabels"]),
    );
    seed(readyForm());
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: `Change: ${MEASUREMENT_LABEL}` }));
    await chooseMeasurement();

    expect(
      await screen.findByText(/confirmation measurement, not a primary one/i),
    ).toBeInTheDocument();
    // Nothing was written to a primary field on the strength of it.
    expect(buildEvolveproInput).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "File as Well / variant labels" }),
    );
    expect(
      screen.getByRole("textbox", { name: ADDITIONAL_LABEL }),
    ).toHaveValue("chosen.xlsx");

    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({
        remeasure_report_xlsx: CHOSEN,
        activity_path: "/project/activity/activity.csv",
      }),
    );
  });

  it("shows the reason and the whole manual choice when the file matches nothing", async () => {
    vi.mocked(detectMeasurementSource).mockResolvedValue(
      detection([], "no label column and no value column in the header"),
    );
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    await chooseMeasurement();

    expect(
      await screen.findByText(/no label column and no value column/i),
    ).toBeInTheDocument();
    for (const format of [
      "Generic long-format",
      "GC data sheet",
      "Raw Agilent report",
      "Numeric-ID Agilent report",
    ]) {
      expect(screen.getByRole("radio", { name: format })).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("radio", { name: "GC data sheet" }));
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ gc_data_xlsx: CHOSEN }),
    );
  });

  it("does not let a failed detection block the work", async () => {
    vi.mocked(detectMeasurementSource).mockRejectedValue(new Error("sidecar is gone"));
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    await chooseMeasurement();

    expect(await screen.findByText(/Format detection did not run/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Raw Agilent report" }));

    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ round1_report_xlsx: CHOSEN }),
    );
  });

  it("always reopens the whole four-way choice from Change, so a detection can be overruled", async () => {
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["longFormat"]));
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    await chooseMeasurement();
    expect(await screen.findByText("Detected: Generic long-format")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: `Change: ${MEASUREMENT_LABEL}` }));
    fireEvent.click(screen.getByRole("radio", { name: "Raw Agilent report" }));

    await build();
    // The same file moved to the field the operator named, and the field it
    // came from was blanked: the backend refuses two primary sources at once.
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ round1_report_xlsx: CHOSEN }),
    );
    expect(buildEvolveproInput).not.toHaveBeenCalledWith(
      expect.objectContaining({ activity_path: expect.anything() }),
    );
  });

  it("drops a detection that answers after another file has been chosen", async () => {
    const second = "/project/activity/second.xlsx";
    let releaseFirst: (value: DetectMeasurementSourceResult) => void = () => {};
    const slow = new Promise<DetectMeasurementSourceResult>((resolve) => {
      releaseFirst = resolve;
    });
    vi.mocked(detectMeasurementSource)
      .mockReturnValueOnce(slow)
      .mockResolvedValueOnce(detection(["longFormat"], "", second));

    seed(readyForm({ activityPath: "" }));
    renderPanel();

    await chooseMeasurement();
    await chooseMeasurement(second);
    expect(await screen.findByText("Detected: Generic long-format")).toBeInTheDocument();

    // The first call answers last, and says something else about a file the
    // operator has already moved on from.
    releaseFirst(detection(["rawReport"]));
    await waitFor(() => expect(detectMeasurementSource).toHaveBeenCalledTimes(2));

    expect(screen.getByText("Detected: Generic long-format")).toBeInTheDocument();
    expect(screen.getByText("second.xlsx")).toBeInTheDocument();
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(
      expect.objectContaining({ activity_path: second }),
    );
  });
});

/**
 * The "?" beside each file field. What it shows is generated out of
 * `templates/` by `scripts/gen_mame_format_preview.py`, so these tests compare
 * the rendered grid against that generated JSON rather than against rows typed
 * out here: a hand-copied expectation keeps passing after the template it
 * describes has changed, which is the failure the preview exists to prevent.
 */
describe("BuildEvolveproInputPanel file-shape previews", () => {
  /** Rendered rows of a preview table, the ellipsis rows dropped. */
  function renderedRows(id: FormatPreviewId): string[][] {
    const table = screen.getByTestId(`format-preview-table-${id}`);
    return within(table)
      .getAllByRole("row")
      .map((row) =>
        within(row)
          .queryAllByRole("cell")
          .map((cell) => cell.textContent ?? ""),
      )
      .filter((cells) => cells.length > 1);
  }

  /** The same rows as the generator wrote them, the header row excluded. */
  function generatedRows(id: FormatPreviewId): string[][] {
    const preview = getFormatPreview(id);
    return preview.windows.flatMap((window, index) =>
      preview.headerRow && index === 0 ? window.rows.slice(1) : window.rows,
    );
  }

  function openPreview(testId: string): void {
    fireEvent.click(screen.getByTestId(`${testId}-trigger`));
  }

  const PRIMARY_IDS: FormatPreviewId[] = [
    "longFormat",
    "gcSheet",
    "rawReport",
    "numericReport",
  ];

  it("offers every accepted format while none has been settled", () => {
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    openPreview("format-preview-measurement");
    for (const id of PRIMARY_IDS) {
      expect(screen.getByTestId(`format-preview-table-${id}`)).toBeInTheDocument();
    }
  });

  it("narrows to the settled format once the file has been read", () => {
    seed(readyForm());
    renderPanel();

    openPreview("format-preview-measurement");
    expect(screen.getByTestId("format-preview-table-longFormat")).toBeInTheDocument();
    for (const id of ["gcSheet", "rawReport", "numericReport"]) {
      expect(screen.queryByTestId(`format-preview-table-${id}`)).toBeNull();
    }
  });

  it("shows the generated rows, not rows written into this test", () => {
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    openPreview("format-preview-measurement");
    let compared = 0;
    for (const id of PRIMARY_IDS) {
      expect(renderedRows(id)).toEqual(generatedRows(id));
      compared += 1;
    }
    expect(compared).toBe(PRIMARY_IDS.length);
  });

  it("marks the one cell that tells the block report formats apart", () => {
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    openPreview("format-preview-measurement");
    // Templates 11 and 12 are the same file down to row 17. A4 against 1 is
    // the whole of the difference, and it is what the mark points at.
    expect(screen.getByTestId("format-preview-highlight-rawReport")).toHaveTextContent(
      "A4",
    );
    expect(
      screen.getByTestId("format-preview-highlight-numericReport"),
    ).toHaveTextContent("1");
  });

  it("names the sample file the loader would have put in the field", () => {
    seed(readyForm());
    renderPanel();

    openPreview("format-preview-measurement");
    const source = getFormatPreview("longFormat").source;
    const name = source.slice(source.lastIndexOf("/") + 1);
    expect(screen.getByText(`Sample file: ${name}`)).toBeInTheDocument();
  });

  it("explains the optional plate layout", () => {
    seed(readyForm({ layoutXlsx: "/project/layout.xlsx" }));
    renderPanel();

    openPreview("format-preview-layout");
    expect(renderedRows("plateLayout")).toEqual(generatedRows("plateLayout"));
  });

  it("explains the designed variant list a numeric screen orders by", () => {
    seed(
      readyForm({
        primarySource: "numericReport",
        activityPath: "",
        numericReportXlsx: "/project/numeric.xlsx",
        expectedXlsx: "/project/expected.xlsx",
      }),
    );
    renderPanel();

    openPreview("format-preview-expected");
    expect(renderedRows("expectedMutations")).toEqual(generatedRows("expectedMutations"));
  });

  it("explains the variant-labeled confirmation report", () => {
    seed(readyForm({ confirmationSource: "variantLabels" }));
    renderPanel();

    openPreview("format-preview-additional");
    expect(renderedRows("confirmationVariantLabels")).toEqual(
      generatedRows("confirmationVariantLabels"),
    );
    expect(
      screen.getByTestId("format-preview-highlight-confirmationVariantLabels"),
    ).toHaveTextContent("65A");
  });

  it("explains the numeric-ID confirmation report", () => {
    seed(readyForm({ confirmationSource: "numericIds" }));
    renderPanel();

    openPreview("format-preview-additional");
    expect(renderedRows("confirmationNumericIds")).toEqual(
      generatedRows("confirmationNumericIds"),
    );
    // The repeat block, not the first sample block: `1-2` is the second
    // measurement of the tube `1` names, which is what a confirmation file is.
    expect(
      screen.getByTestId("format-preview-highlight-confirmationNumericIds"),
    ).toHaveTextContent("1-2");
  });

  it("does not show the same table for the numeric screen and its confirmation", () => {
    // Both read template 12, and taking the first sample block for each made
    // the two panels identical: a reader holding one of the files could open
    // either "?" and see the other one's rows.
    seed(readyForm({ primarySource: "numericReport", activityPath: "", numericReportXlsx: "/project/numeric.xlsx", expectedXlsx: "/project/expected.xlsx" }));
    renderPanel();
    openPreview("format-preview-measurement");
    const primary = renderedRows("numericReport");

    cleanup();
    seed(readyForm({ confirmationSource: "numericIds" }));
    renderPanel();
    openPreview("format-preview-additional");
    const confirmation = renderedRows("confirmationNumericIds");

    expect(primary).not.toEqual(confirmation);
    expect(getFormatPreview("numericReport").source).toBe(
      getFormatPreview("confirmationNumericIds").source,
    );
  });

  it("says what the two numeric formats count, which no table can show", () => {
    seed(readyForm({ confirmationSource: "numericIds" }));
    renderPanel();

    openPreview("format-preview-additional");
    expect(
      screen.getByText(
        "ID j counts only the variants the primary screen measured above wild type, numbered in that same plate order, and each is measured again.",
      ),
    ).toBeInTheDocument();
  });

  it("gives the output path no '?' at all", () => {
    seed(readyForm({ activityPath: "" }));
    renderPanel();

    // Negative control: the app writes the output, so there is no file for the
    // operator to shape. Only the input fields carry a preview.
    const triggers = screen
      .queryAllByTestId(/^format-preview-.*-trigger$/)
      .map((node) => node.getAttribute("data-testid"));
    expect(triggers).not.toContain("format-preview-output-trigger");
    expect(triggers.length).toBeGreaterThan(0);
  });

  it("closes on Escape and gives focus back to the trigger", () => {
    seed(readyForm());
    renderPanel();

    const trigger = screen.getByTestId("format-preview-measurement-trigger");
    fireEvent.click(trigger);
    expect(screen.getByTestId("format-preview-table-longFormat")).toBeInTheDocument();
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByTestId("format-preview-table-longFormat")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("puts no preview on the verdict or the output, which the app fills", () => {
    seed(readyForm());
    renderPanel();

    expect(screen.queryByTestId("format-preview-verdict-trigger")).toBeNull();
    expect(screen.queryByTestId("format-preview-output-trigger")).toBeNull();
    // Only the fields the operator brings a file to: the measurement and the
    // optional plate layout (rendered inside its collapsed disclosure).
    expect(
      screen.getAllByTestId(/^format-preview-.+-trigger$/).map((el) => el.dataset.testid),
    ).toEqual([
      "format-preview-measurement-trigger",
      "format-preview-additional-trigger",
      "format-preview-layout-trigger",
    ]);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function chooseAdditional(path = CHOSEN): Promise<void> {
  vi.mocked(open).mockResolvedValueOnce(path);
  fireEvent.click(screen.getByRole("button", { name: `Browse ${ADDITIONAL_LABEL}` }));
  await waitFor(() => expect(detectMeasurementSource).toHaveBeenCalledWith({ measurement_path: path }));
}

function additionalRegion() {
  return within(screen.getByRole("region", { name: ADDITIONAL_LABEL }));
}

describe("BuildEvolveproInputPanel sibling additional experiment file", () => {
  it("shows the optional file alongside the primary without a prerequisite format toggle", () => {
    seed(readyForm({ activityPath: "" }));
    renderPanel();
    expect(screen.getByRole("heading", { name: "Convert EVOLVEpro input file" })).toBeInTheDocument();
    expect(screen.getByLabelText(MEASUREMENT_LABEL)).toHaveValue("");
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
    expect(screen.getByRole("button", { name: `Browse ${ADDITIONAL_LABEL}` })).toBeEnabled();
    expect(screen.queryByRole("radiogroup", { name: "Additional measurement format" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "None" })).not.toBeInTheDocument();
  });

  it("autodetects a variant confirmation, retains the primary, and persists the established shape", async () => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["confirmationVariantLabels"]));
    const view = renderPanel();
    await chooseAdditional();
    expect(await screen.findByText("Detected: Well / variant labels")).toBeInTheDocument();
    expect(loadBuildEvolveproFromStorage(PROJECT)).toMatchObject({
      confirmationSource: "variantLabels", remeasureReportXlsx: CHOSEN,
      activityPath: "/project/activity/activity.csv", remeasureNumericXlsx: "",
    });
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      activity_path: "/project/activity/activity.csv", remeasure_report_xlsx: CHOSEN,
      remeasure_numeric_xlsx: undefined,
    }));
    view.unmount();
    vi.mocked(detectMeasurementSource).mockClear();
    renderPanel();
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("chosen.xlsx");
    expect(screen.getByText("Format: Well / variant labels")).toBeInTheDocument();
    expect(screen.queryByText("Detected: Well / variant labels")).not.toBeInTheDocument();
    expect(detectMeasurementSource).not.toHaveBeenCalled();
  });

  it.each(["primary", "additional"] as const)("requires an explicit role for well labels browsed in the %s slot", async (slot) => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["rawReport", "confirmationWellLabels"]));
    renderPanel();
    if (slot === "primary") {
      fireEvent.click(screen.getByRole("button", { name: `Change: ${MEASUREMENT_LABEL}` }));
      await chooseMeasurement();
    } else await chooseAdditional();
    expect(await screen.findByText(/same well-labeled report can be the primary experiment/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(loadBuildEvolveproFromStorage(PROJECT).confirmationSource).toBe("none");
    fireEvent.click(screen.getByRole("radio", { name: "Well / variant labels" }));
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      activity_path: "/project/activity/activity.csv", remeasure_report_xlsx: CHOSEN,
    }));
  });

  it("can explicitly move a well report from the additional slot to the primary slot", async () => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["rawReport", "confirmationWellLabels"]));
    renderPanel();
    await chooseAdditional();
    fireEvent.click(await screen.findByRole("radio", { name: "Raw Agilent report" }));
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      round1_report_xlsx: CHOSEN, remeasure_report_xlsx: undefined,
    }));
  });

  it("requires numeric above-WT confirmation even if the detector returns it alone", async () => {
    seed(readyForm({ expectedXlsx: "/project/expected.xlsx" }));
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["confirmationNumericIds"]));
    renderPanel();
    await chooseAdditional();
    expect(await screen.findByText(/ID j counts only the variants/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(loadBuildEvolveproFromStorage(PROJECT).confirmationSource).toBe("none");
    fireEvent.click(screen.getByRole("button", { name: "File as Numeric-ID replicate report" }));
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      remeasure_numeric_xlsx: CHOSEN, expected_xlsx: "/project/expected.xlsx",
    }));
  });

  it("preserves the explicit numeric order-source gate after additional-file detection", async () => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["numericReport", "confirmationNumericIds"]));
    renderPanel();
    await chooseAdditional();
    fireEvent.click(await screen.findByRole("radio", { name: "Numeric-ID replicate report" }));
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(screen.getByLabelText("Designed variant list")).toHaveValue("");
  });

  it.each(["no match", "failure"])("keeps manual additional-format selection available after %s", async (outcome) => {
    seed(readyForm());
    if (outcome === "failure") vi.mocked(detectMeasurementSource).mockRejectedValue(new Error("sidecar unavailable"));
    else vi.mocked(detectMeasurementSource).mockResolvedValue(detection([], "No supported sample labels"));
    renderPanel();
    await chooseAdditional();
    const format = await screen.findByRole("radio", { name: "Well / variant labels" });
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(screen.queryByRole("list", { name: "File detection summary" })).not.toBeInTheDocument();
    fireEvent.click(format);
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({ remeasure_report_xlsx: CHOSEN }));
  });

  it("can manually override an ambiguous result without forcing its candidates", async () => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["rawReport", "confirmationWellLabels"]));
    renderPanel();
    await chooseAdditional();
    fireEvent.click(await additionalRegion().findByRole("button", { name: "Choose format manually" }));
    expect(screen.queryByRole("radio", { name: "Raw Agilent report" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Well / variant labels" }));
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeEnabled();
  });

  it("does not overwrite the primary when a primary-only file is browsed as additional", async () => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["longFormat"]));
    renderPanel();
    await chooseAdditional();
    expect(await screen.findByText(/matches a primary experiment format/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    expect(loadBuildEvolveproFromStorage(PROJECT).activityPath).toBe("/project/activity/activity.csv");
    fireEvent.click(screen.getByRole("button", { name: "Use as experiment data: Generic long-format" }));
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
    expect(loadBuildEvolveproFromStorage(PROJECT).activityPath).toBe(CHOSEN);
  });

  it.each(["variantLabels", "numericIds"] as const)("restores and removes %s without resurrecting inactive paths", async (confirmationSource) => {
    seed(readyForm({
      confirmationSource, remeasureReportXlsx: "/project/wells.xlsx",
      remeasureNumericXlsx: "/project/numeric.xlsx", expectedXlsx: "/project/expected.xlsx",
    }));
    renderPanel();
    expect(detectMeasurementSource).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue(
      confirmationSource === "variantLabels" ? "wells.xlsx" : "numeric.xlsx",
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove additional file" }));
    expect(loadBuildEvolveproFromStorage(PROJECT)).toMatchObject({
      confirmationSource: "none", remeasureReportXlsx: "", remeasureNumericXlsx: "",
    });
    expect(screen.queryByLabelText("Mismatch threshold")).not.toBeInTheDocument();
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      remeasure_report_xlsx: undefined, remeasure_numeric_xlsx: undefined,
    }));
  });

  it("shows real summaries independently for each file without describing validated variants", async () => {
    seed(readyForm({ activityPath: "" }));
    vi.mocked(detectMeasurementSource)
      .mockResolvedValueOnce({ ...detection(["rawReport"]), evidence: {
        n_sample_rows: 23, n_recognized_rows: 21, n_control_rows: 4, n_unique_labels: 7,
      } })
      .mockResolvedValueOnce({ ...detection(["confirmationVariantLabels"]), evidence: {
        n_sample_rows: 5, n_skipped_rows: 0,
      } });
    renderPanel();
    await chooseMeasurement();
    await chooseAdditional("/project/additional.xlsx");
    expect(await screen.findByText("Sample rows: 5")).toBeInTheDocument();
    expect(screen.getByText("Sample rows: 23")).toBeInTheDocument();
    expect(screen.getByText("Recognized labels: 21 rows")).toBeInTheDocument();
    expect(screen.getByText("Unique sample labels: 7")).toBeInTheDocument();
    expect(screen.getByText("WT control rows: 4")).toBeInTheDocument();
    expect(additionalRegion().getByText("Skipped rows: 0")).toBeInTheDocument();
    expect(additionalRegion().queryByText(/Recognized labels|Unique sample labels/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("list", { name: "File detection summary" })).toHaveLength(2);
    expect(screen.queryByText(/valid variants/i)).not.toBeInTheDocument();
  });

  it.each([
    {},
    { n_sample_rows: "12", n_recognized_rows: null, n_skipped_rows: -1, n_unique_labels: NaN },
    { n_sample_rows: Infinity, n_recognized_rows: 0.5 },
  ])("omits absent or invalid count evidence rather than fabricating zeros: %j", async (evidence) => {
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockResolvedValue({ ...detection(["confirmationVariantLabels"]), evidence });
    renderPanel();
    await chooseAdditional();
    await screen.findByText("Detected: Well / variant labels");
    expect(screen.queryByRole("list", { name: "File detection summary" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Sample rows: 0|Unique sample labels: 0/)).not.toBeInTheDocument();
  });

  it("previews actual well, variant, and numeric confirmation shapes from the optional field", () => {
    seed(readyForm());
    renderPanel();
    fireEvent.click(screen.getByTestId("format-preview-additional-trigger"));
    for (const id of ["confirmationWellLabels", "confirmationVariantLabels", "confirmationNumericIds"] as const) {
      const rows = within(screen.getByTestId(`format-preview-table-${id}`)).getAllByRole("row")
        .map((row) => within(row).queryAllByRole("cell").map((cell) => cell.textContent ?? ""))
        .filter((cells) => cells.length > 1);
      const preview = getFormatPreview(id);
      expect(rows).toEqual(preview.windows.flatMap((window, index) => preview.headerRow && index === 0 ? window.rows.slice(1) : window.rows));
    }
  });
});

describe("BuildEvolveproInputPanel independent detection lifetimes", () => {
  it("does not let a delayed additional result replace a newer choice", async () => {
    const old = deferred<DetectMeasurementSourceResult>();
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(detection(["confirmationVariantLabels"], "", "/project/new.xlsx"));
    renderPanel();
    await chooseAdditional("/project/old.xlsx");
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    await chooseAdditional("/project/new.xlsx");
    await screen.findByText("Detected: Well / variant labels");
    await act(async () => old.resolve(detection(["confirmationNumericIds"], "", "/project/old.xlsx")));
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("new.xlsx");
    expect(loadBuildEvolveproFromStorage(PROJECT).remeasureReportXlsx).toBe("/project/new.xlsx");
  });

  it("keeps primary and additional requests independent when they resolve in reverse order", async () => {
    const primary = deferred<DetectMeasurementSourceResult>();
    const additional = deferred<DetectMeasurementSourceResult>();
    seed(readyForm({ activityPath: "" }));
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(primary.promise).mockReturnValueOnce(additional.promise);
    renderPanel();
    await chooseMeasurement("/project/primary.csv");
    await chooseAdditional("/project/additional.xlsx");
    await act(async () => additional.resolve(detection(["confirmationVariantLabels"], "", "/project/additional.xlsx")));
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
    await act(async () => primary.resolve(detection(["longFormat"], "", "/project/primary.csv")));
    await build();
    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      activity_path: "/project/primary.csv", remeasure_report_xlsx: "/project/additional.xlsx",
    }));
  });

  it("ignores an additional detector rejection after the optional file is removed", async () => {
    const request = deferred<DetectMeasurementSourceResult>();
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(request.promise);
    renderPanel();
    await chooseAdditional();
    fireEvent.click(screen.getByRole("button", { name: "Remove additional file" }));
    await act(async () => request.reject(new Error("Old error must stay hidden")));
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
    expect(screen.queryByText(/Old error must stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Additional measurement format" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeEnabled();
  });

  it("ignores pending detection after clearing restored inputs", async () => {
    const request = deferred<DetectMeasurementSourceResult>();
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(request.promise);
    renderPanel();
    await chooseAdditional();
    fireEvent.click(screen.getByRole("button", { name: "Clear restored EVOLVEpro inputs" }));
    await act(async () => request.resolve(detection(["confirmationVariantLabels"])));
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
    expect(loadBuildEvolveproFromStorage(PROJECT).confirmationSource).toBe("none");
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeDisabled();
  });

  it("ignores both detectors after a global reset", async () => {
    const primary = deferred<DetectMeasurementSourceResult>();
    const additional = deferred<DetectMeasurementSourceResult>();
    seed(readyForm({ activityPath: "" }));
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(primary.promise).mockReturnValueOnce(additional.promise);
    const view = renderPanel();
    await chooseMeasurement();
    await chooseAdditional("/project/additional.xlsx");
    mockMameState.resetEpoch = 1;
    view.rerender(<ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}><BuildEvolveproInputPanel /></ProjectProvider>);
    await act(async () => {
      primary.resolve(detection(["rawReport"]));
      additional.resolve(detection(["confirmationVariantLabels"], "", "/project/additional.xlsx"));
    });
    expect(screen.getByLabelText(MEASUREMENT_LABEL)).toHaveValue("");
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
    expect(loadBuildEvolveproFromStorage(PROJECT).confirmationSource).toBe("none");
  });

  it("ignores an additional result from the previous project", async () => {
    const request = deferred<DetectMeasurementSourceResult>();
    seed(readyForm());
    saveBuildEvolveproToStorage({ ...readyForm(), activityPath: "/other/kept.csv", remeasureReportXlsx: "/other/kept.xlsx", confirmationSource: "variantLabels" }, "/other");
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(request.promise);
    const view = renderPanel();
    await chooseAdditional();
    view.rerender(<ProjectProvider value={{ path: "/other", name: "Other", scratch: false }}><BuildEvolveproInputPanel /></ProjectProvider>);
    await act(async () => request.resolve(detection(["confirmationVariantLabels"])));
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("kept.xlsx");
    expect(loadBuildEvolveproFromStorage("/other").remeasureReportXlsx).toBe("/other/kept.xlsx");
  });

  it("keeps an in-flight detection alive when a second browse is canceled", async () => {
    const request = deferred<DetectMeasurementSourceResult>();
    seed(readyForm());
    vi.mocked(detectMeasurementSource).mockReturnValueOnce(request.promise);
    renderPanel();
    await chooseAdditional();
    vi.mocked(open).mockResolvedValueOnce(null);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: `Browse ${ADDITIONAL_LABEL}` })));
    await act(async () => request.resolve(detection(["confirmationVariantLabels"])));
    expect(screen.getByText("Detected: Well / variant labels")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build EVOLVEpro input" })).toBeEnabled();
  });

  it("does not apply a native picker result returned after reset", async () => {
    const dialog = deferred<string | null>();
    seed(readyForm());
    vi.mocked(open).mockReturnValueOnce(dialog.promise);
    const view = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: `Browse ${ADDITIONAL_LABEL}` }));
    mockMameState.resetEpoch = 1;
    view.rerender(<ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}><BuildEvolveproInputPanel /></ProjectProvider>);
    await act(async () => dialog.resolve(CHOSEN));
    expect(detectMeasurementSource).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
  });

  it.each(["success", "failure"])("does not surface a stale build %s after an additional file is chosen", async (outcome) => {
    const request = deferred<BuildEvolveproInputResult>();
    seed(readyForm());
    vi.mocked(buildEvolveproInput).mockReturnValueOnce(request.promise);
    vi.mocked(detectMeasurementSource).mockResolvedValue(detection(["confirmationVariantLabels"]));
    renderPanel();
    await build();
    await chooseAdditional();
    await screen.findByText("Detected: Well / variant labels");
    await act(async () => {
      if (outcome === "success") request.resolve(RESULT);
      else request.reject(new Error(LABEL_SWAP_MESSAGE));
    });
    expect(screen.queryByRole("heading", { name: "Build result" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Allow reviewed label mismatch" })).not.toBeInTheDocument();
    expect(mockSetBuildEvolveproCompletion.mock.calls.every(([completion]) => completion === null)).toBe(true);
  });
});

it("ignores an additional detection when the active round changes", async () => {
  const request = deferred<DetectMeasurementSourceResult>();
  seed(readyForm());
  vi.mocked(detectMeasurementSource).mockReturnValueOnce(request.promise);
  renderPanel();
  await chooseAdditional();
  await act(async () => useRoundStore.setState({ active_round_id: "next-round" }));
  await act(async () => request.resolve(detection(["confirmationVariantLabels"])));
  expect(screen.getByRole("textbox", { name: ADDITIONAL_LABEL })).toHaveValue("");
  expect(loadBuildEvolveproFromStorage(PROJECT).confirmationSource).toBe("none");
});
