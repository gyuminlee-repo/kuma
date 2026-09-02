import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

const MEASUREMENT_LABEL = "Measurement file";
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
      screen.getByLabelText("Confirmation report xlsx (numeric IDs)"),
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
      screen.getByRole("button", { name: "File as Variant-labeled Agilent report" }),
    );
    expect(
      screen.getByLabelText("Confirmation report xlsx (variant-labeled)"),
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
