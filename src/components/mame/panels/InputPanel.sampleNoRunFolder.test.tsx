/**
 * InputPanel.sampleNoRunFolder.test.tsx
 *
 * Regression coverage for defect 3 (task notes, "MAME sample data
 * triplicate"): `loadSampleData` never calls `setInputDir` (the bundle ships
 * no MinKNOW run folder, left out for size), so the run-folder field at the
 * top of step 2 stays empty while the other three fields fill in. Without an
 * explanation this reads exactly like an operator's own unfinished pick.
 *
 * Only the notice-swap behaviour is covered here; it does not depend on
 * fixture shape (well count, verdict classes, native barcodes), which is
 * being regenerated concurrently by another change.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));
vi.mock("@/hooks/useAutosaveHydration", () => ({ applyMameAutoDetect: vi.fn() }));
vi.mock("@/lib/mame/detectProjectFiles", () => ({ detectFromInputDir: vi.fn() }));
vi.mock("@/lib/overwriteConfirm", () => ({
  fileExists: vi.fn().mockResolvedValue(false),
  requestOverwriteConfirm: vi.fn().mockResolvedValue(true),
}));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("@/lib/ipc-mame", () => ({ sendRequest: vi.fn() }));
vi.mock("sonner", () => ({ toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() } }));

type MockMameState = {
  inputDir: string;
  inputMode: "consensus" | "sorted_barcode" | "raw_run";
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  rawRunParams: { customBarcodesPath: string; sequencingSummaryPath: string };
  barcodeAxisCounts: null;
  sampleDataLoaded: boolean;
  verdicts: unknown[];
  setInputDir: () => void;
  setExpectedPath: () => void;
  checkExpectedPlateOrder: () => Promise<void>;
  setReferencePath: () => void;
  setOutputPath: () => void;
  setParams: () => void;
  inspectVariantSource: () => Promise<void>;
  variantSourceInfo: null;
  variantSheet: null;
  variantColumn: null;
  setVariantSheet: () => void;
  setVariantColumn: () => void;
};

function baseState(overrides: Partial<MockMameState> = {}): MockMameState {
  return {
    inputDir: "",
    inputMode: "raw_run",
    expectedPath: "/resolved/samples/mame/03_mame_expected_mutations.xlsx",
    referencePath: "/resolved/samples/mame/egfp_with_flanks.fa",
    outputPath: "",
    rawRunParams: { customBarcodesPath: "", sequencingSummaryPath: "" },
    barcodeAxisCounts: null,
    sampleDataLoaded: false,
    verdicts: [],
    setInputDir: vi.fn(),
    setExpectedPath: vi.fn(),
    checkExpectedPlateOrder: vi.fn(),
    setReferencePath: vi.fn(),
    setOutputPath: vi.fn(),
    setParams: vi.fn(),
    inspectVariantSource: vi.fn(),
    variantSourceInfo: null,
    variantSheet: null,
    variantColumn: null,
    setVariantSheet: vi.fn(),
    setVariantColumn: vi.fn(),
    ...overrides,
  };
}

let mockState: MockMameState = baseState();

vi.mock("@/store/mame/mameAppStore", () => ({
  useMameAppStore: Object.assign(
    (selector: (s: MockMameState) => unknown) => selector(mockState),
    { getState: () => mockState },
  ),
}));

import { InputPanel } from "./InputPanel";

function renderPanel() {
  return render(
    <ProjectProvider value={{ path: "/project", name: "Demo", scratch: false }}>
      <InputPanel />
    </ProjectProvider>,
  );
}

describe("InputPanel sample-data run-folder notice (defect 3 regression)", () => {
  it("shows the ordinary 'no path selected' text before any sample data is loaded", () => {
    mockState = baseState({ sampleDataLoaded: false, inputDir: "" });
    renderPanel();

    // Every empty FileField (run folder, export destination) reads the same
    // generic text before any sample data has been loaded.
    expect(screen.getAllByText("No path selected").length).toBeGreaterThan(0);
    expect(
      screen.queryByText(
        "Sample data has no raw run folder (left out to keep the bundle small). The results below are pre-computed.",
      ),
    ).not.toBeInTheDocument();
  });

  it("swaps in the sample-bundle explanation once sampleDataLoaded is true and inputDir is still empty", () => {
    mockState = baseState({ sampleDataLoaded: true, inputDir: "" });
    renderPanel();

    expect(
      screen.getByText(
        "Sample data has no raw run folder (left out to keep the bundle small). The results below are pre-computed.",
      ),
    ).toBeInTheDocument();
    // The unrelated export-destination field (also empty here) must keep the
    // generic text: only the run-folder field at the top is swapped.
    expect(screen.getAllByText("No path selected").length).toBeGreaterThan(0);
  });

  it("does not override the label once the operator (or auto-detect) has actually filled inputDir", () => {
    mockState = baseState({ sampleDataLoaded: true, inputDir: "/some/minknow/run" });
    renderPanel();

    expect(
      screen.queryByText(
        "Sample data has no raw run folder (left out to keep the bundle small). The results below are pre-computed.",
      ),
    ).not.toBeInTheDocument();
  });

  it("applies the same swap across every inputMode, since loadSampleData never sets inputMode", () => {
    for (const inputMode of ["consensus", "sorted_barcode", "raw_run"] as const) {
      mockState = baseState({ sampleDataLoaded: true, inputDir: "", inputMode });
      const { unmount } = renderPanel();

      expect(
        screen.getByText(
          "Sample data has no raw run folder (left out to keep the bundle small). The results below are pre-computed.",
        ),
      ).toBeInTheDocument();
      unmount();
    }
  });
});
