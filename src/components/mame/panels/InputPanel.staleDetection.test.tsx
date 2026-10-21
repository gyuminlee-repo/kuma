/**
 * A run-folder scan fills the inputs of the project and folder it started for.
 *
 * Picking a run folder scans it for the reference, the expected workbook and
 * the barcode files. The scan used to fill whatever was on screen when it
 * returned, so a scan started in project A wrote A's files into project B, and
 * a scan of a folder the user had since replaced filled the new folder's
 * inputs with the old folder's files.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";

const mocks = vi.hoisted(() => ({ open: vi.fn(), detect: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open, save: vi.fn() }));
vi.mock("@/hooks/useAutosaveHydration", () => ({ applyMameAutoDetect: vi.fn() }));
vi.mock("@/lib/mame/detectProjectFiles", () => ({ detectFromInputDir: mocks.detect }));
vi.mock("@/lib/overwriteConfirm", () => ({
  fileExists: vi.fn().mockResolvedValue(false),
  requestOverwriteConfirm: vi.fn().mockResolvedValue(true),
}));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("@/lib/ipc-mame", () => ({ sendRequest: vi.fn() }));
vi.mock("sonner", () => ({ toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() } }));

const state: Record<string, unknown> = {};
vi.mock("@/store/mame/mameAppStore", () => ({
  useMameStoreApi: () => ({ getState: () => state }),
  useMameAppStore: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) => selector(state),
    { getState: () => state },
  ),
}));

import { InputPanel } from "./InputPanel";

const DETECTED = {
  referencePath: "/projectA/run/reference.fasta",
  expectedPath: "",
  legacySampleMapPath: "",
  customBarcodesPath: "",
  sequencingSummaryPath: "",
};

beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(state, {
    inputDir: "",
    inputMode: "raw_run",
    expectedPath: "",
    referencePath: "",
    outputPath: "",
    legacySampleMapPath: "",
    rawRunParams: { customBarcodesPath: "", sequencingSummaryPath: "" },
    barcodeAxisCounts: null,
    sampleDataLoaded: false,
    verdicts: [],
    resetEpoch: 0,
    setInputDir: vi.fn((value: string) => { state.inputDir = value; }),
    chooseExpectedPath: vi.fn(),
    setReferencePath: vi.fn(),
    setLegacySampleMapPath: vi.fn(),
    setOutputPath: vi.fn(),
    setParams: vi.fn(),
    inspectVariantSource: vi.fn(),
    variantSourceInfo: null,
    variantSheet: null,
    variantColumn: null,
    setVariantSheet: vi.fn(),
    setVariantColumn: vi.fn(),
  });
  mocks.open.mockResolvedValue("/projectA/run");
});
afterEach(cleanup);

function panel(path: string) {
  return <ProjectProvider value={{ path, name: "P", scratch: false }}><InputPanel /></ProjectProvider>;
}

async function browseRunFolder(): Promise<(value: unknown) => Promise<void>> {
  let release!: (value: unknown) => void;
  const detection = new Promise((resolve) => { release = resolve; });
  mocks.detect.mockReturnValue(detection);
  const button = screen.getAllByRole("button").find((b) => /MinKNOW|run folder/i.test(b.getAttribute("aria-label") ?? ""));
  expect(button).toBeDefined();
  if (button) fireEvent.click(button);
  await waitFor(() => expect(mocks.detect).toHaveBeenCalledWith("/projectA/run"));
  return async (value) => {
    await act(async () => {
      release(value);
      await detection;
    });
  };
}

describe("run-folder scan", () => {
  it("fills the folder's files when nothing changed meanwhile", async () => {
    render(panel("/projectA"));
    const release = await browseRunFolder();
    await release(DETECTED);
    await waitFor(() => expect(state.setReferencePath).toHaveBeenCalledWith(DETECTED.referencePath));
  });

  it("fills nothing once another project is open", async () => {
    const view = render(panel("/projectA"));
    const release = await browseRunFolder();
    view.rerender(panel("/projectB"));
    await release(DETECTED);
    expect(state.setReferencePath).not.toHaveBeenCalled();
  });

  it("fills nothing once a reset happened", async () => {
    const view = render(panel("/projectA"));
    const release = await browseRunFolder();
    state.resetEpoch = 1;
    view.rerender(panel("/projectA"));
    await release(DETECTED);
    expect(state.setReferencePath).not.toHaveBeenCalled();
  });

  it("fills nothing once the user picked another folder", async () => {
    render(panel("/projectA"));
    const release = await browseRunFolder();
    state.inputDir = "/projectA/other-run";
    await release(DETECTED);
    expect(state.setReferencePath).not.toHaveBeenCalled();
  });
});
