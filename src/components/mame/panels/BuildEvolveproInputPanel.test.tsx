import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";

const mockSetBuildEvolveproCompletion = vi.hoisted(() => vi.fn());
const mockMkdir = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: mockMkdir }));
vi.mock("@/lib/ipc-mame", () => ({ buildEvolveproInput: vi.fn() }));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("@/lib/workspace", () => ({ registerArtifacts: vi.fn().mockResolvedValue(undefined) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/store/mame/mameAppStore", () => ({
  useMameAppStore: (selector: (state: { resetEpoch: number; setBuildEvolveproCompletion: typeof mockSetBuildEvolveproCompletion }) => unknown) =>
    selector({ resetEpoch: 0, setBuildEvolveproCompletion: mockSetBuildEvolveproCompletion }),
}));

import { buildEvolveproInput } from "@/lib/ipc-mame";
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

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  mockMkdir.mockResolvedValue(undefined);
  vi.mocked(buildEvolveproInput).mockResolvedValue(RESULT);
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

  it("sends reviewed-label-mismatch acknowledgement", async () => {
    seed(readyForm());
    renderPanel();

    fireEvent.click(screen.getByRole("checkbox", { name: "Allow reviewed label mismatch" }));
    await build();

    expect(buildEvolveproInput).toHaveBeenCalledWith(expect.objectContaining({
      allow_label_mismatch: true,
    }));
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
