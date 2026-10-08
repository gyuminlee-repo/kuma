/**
 * `selectCanRun` gates the Run button, so what it lets through has to be a
 * configuration the sidecar can actually start. These cover the one path where
 * it disagreed with the sidecar: raw-run mode, which sends
 * `expected: state.expectedPath` like every other mode (`inputSlice.ts:651`)
 * while the selector treated that field as optional.
 */
import { describe, expect, it } from "vitest";
import { selectCanRun } from "./selectors";
import type { AppState } from "./types";

/** Everything `selectCanRun` reads, in the state a ready raw run is in. */
function rawRunState(overrides: Partial<AppState> = {}): AppState {
  return {
    inputMode: "raw_run",
    inputDir: "/runs/minknow",
    expectedPath: "/proj/expected.xlsx",
    referencePath: "/proj/ref.fasta",
    outputPath: "/proj/out",
    rawRunParams: { customBarcodesPath: "/proj/barcodes.xlsx" },
    isAnalyzing: false,
    isValidating: false,
    validationErrors: [],
    plateOrderFinding: null,
    selectedWells: null,
    wellSelectionOccupants: null,
    ...overrides,
  } as unknown as AppState;
}

describe("selectCanRun", () => {
  it("enables the run when a raw run has every path the sidecar reads", () => {
    expect(selectCanRun(rawRunState())).toBe(true);
  });

  it("refuses a raw run with no expected workbook", () => {
    // `handle_analyze` resolves `params["expected"]` through `_validate_filepath`
    // before it looks at the input dir at all (`analyze.py:1224`), and an empty
    // string there raises `filepath is required` from inside the sidecar. With
    // the button enabled the operator gets that sentence instead of a field.
    expect(selectCanRun(rawRunState({ expectedPath: "" }))).toBe(false);
  });

  it("refuses a consensus run with no expected workbook", () => {
    expect(
      selectCanRun(rawRunState({ inputMode: "consensus", expectedPath: "" })),
    ).toBe(false);
  });

  it("still refuses a raw run with no barcode workbook", () => {
    expect(
      selectCanRun(rawRunState({ rawRunParams: { customBarcodesPath: "" } as AppState["rawRunParams"] })),
    ).toBe(false);
  });
});
