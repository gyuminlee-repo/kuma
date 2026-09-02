/**
 * The two step 1 file fields show the shape of the file they want.
 *
 * Custom barcodes and the expected-variant list are workbooks the operator
 * builds elsewhere and brings in. Both already carried a sentence of help; the
 * sentence says what the file is for and never what it looks like, which is
 * what somebody staring at an empty spreadsheet needs. The rows compared here
 * come from the generated JSON, never from this file.
 *
 * The run-folder field is the negative control: it takes a directory, so there
 * is no shape to show and it must carry no "?".
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import {
  generatedRows,
  openPreview,
  previewTriggerIds,
  renderedRows,
} from "@/components/ui/formatPreviewTestUtils";

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

type MockMameState = Record<string, unknown>;

/** Raw-run mode, which is the only mode that renders the barcode field. */
const mockState: MockMameState = {
  inputDir: "",
  inputMode: "raw_run",
  expectedPath: "",
  referencePath: "",
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
};

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

describe("MAME step 1 file-shape previews", () => {
  it("shows the custom-barcode workbook as the generator read it", () => {
    renderPanel();

    openPreview("format-preview-custom-barcodes");
    expect(renderedRows("customBarcodes")).toEqual(generatedRows("customBarcodes"));
  });

  it("shows the expected-variant list as the generator read it", () => {
    renderPanel();

    openPreview("format-preview-expected-variants");
    expect(renderedRows("expectedMutations")).toEqual(
      generatedRows("expectedMutations"),
    );
  });

  it("keeps the sentence that used to sit in a second '?' inside the same panel", () => {
    renderPanel();

    // One control, not two: the prose and the table answer the same question
    // and a reader offered two identical buttons cannot tell them apart.
    expect(previewTriggerIds().sort()).toEqual([
      "format-preview-custom-barcodes-trigger",
      "format-preview-expected-variants-trigger",
    ]);
    openPreview("format-preview-custom-barcodes");
    expect(
      screen.getByText(
        "Raw MinKNOW run mode uses this file to assign reads to per-well FASTA outputs before analysis.",
      ),
    ).toBeInTheDocument();
  });

  it("closes on Escape and puts focus back on the trigger", () => {
    renderPanel();

    const trigger = screen.getByTestId("format-preview-custom-barcodes-trigger");
    openPreview("format-preview-custom-barcodes");
    expect(screen.getByTestId("format-preview-custom-barcodes")).toBeInTheDocument();

    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByTestId("format-preview-custom-barcodes")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("gives the reference and run-folder fields no '?' at all", () => {
    renderPanel();

    // Negative control: this panel also renders a run folder (a directory) and
    // a reference sequence (fasta or GenBank). Neither is a table, so the two
    // "?" on screen are the two table fields and nothing else.
    expect(previewTriggerIds().sort()).toEqual([
      "format-preview-custom-barcodes-trigger",
      "format-preview-expected-variants-trigger",
    ]);
  });
});
