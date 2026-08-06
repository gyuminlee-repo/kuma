/**
 * The plate-order finding, at the store layer.
 *
 * A KURO export writes the same plate on `Fwd List`/`Fwd Plate` and on
 * `expected_mutations`. When they disagree and MAME reads wells off the
 * expected sheet's row order, every verdict lands on the wrong well and nothing
 * in the output says so (2026-08-04, 94 wells).
 *
 * v0.15.6 let such a run proceed with a note beside it, on the reasoning that
 * the operator names the rows to read. 2026-08-05 took that back: naming rows
 * is not the same as recording which of the workbook's two plates went into the
 * tubes, and no input on the screen records it. So the finding blocks the run
 * and the way out is a different workbook. These cover that the finding is
 * asked for, that it holds the run whichever path stored it, and that picking
 * another file releases it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { selectCanRun, selectPlateOrderSeverity } from "../selectors";
import { createInputSlice } from "./inputSlice";
import { createAnalysisSliceDoubles } from "./testHelpers/analysisSliceDoubles";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

/** A disagreement the sidecar could compare, without a severity. */
const REPORT = {
  comparable: true,
  mismatched: true,
  plate_sheet: "Fwd List",
  examples: [{ well: "A2", plate: "K53I", expected: "I92D" }],
  missing_from_expected: ["Q17R"],
  absent_from_plate: [],
};

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = {
    ...createAnalysisSliceDoubles(),
    ...initial,
  };
  const set = (
    updater: Partial<AppState> | ((current: AppState) => Partial<AppState>),
  ) => {
    const updates = typeof updater === "function" ? updater(state as AppState) : updater;
    Object.assign(state, updates);
  };
  const get = () => state as AppState;
  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  );
  Object.assign(state, slice, initial);
  return state as AppState;
}

/** A store whose only reason not to run is whatever the test sets up. */
function makeRunnableStore(initial: Partial<AppState> = {}) {
  return makeStore({
    inputDir: "D:/project/consensus",
    expectedPath: "D:/project/KURO_expected.xlsx",
    referencePath: "D:/project/ref.fasta",
    outputPath: "D:/project",
    inputMode: "consensus",
    ...initial,
  });
}

describe("mame inputSlice plate-order finding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends the layout inputs with validate_inputs", async () => {
    const store = makeRunnableStore({
      sampleMapPath: "D:/project/sample_map.xlsx",
      wellLayout: { A1: "K53I" },
    });
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    expect(mockSendRequest).toHaveBeenCalledWith(
      "validate_inputs",
      expect.objectContaining({
        sample_map_xlsx: "D:/project/sample_map.xlsx",
        well_layout: { A1: "K53I" },
      }),
    );
  });

  it("sends null for layout inputs that were never chosen", async () => {
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    expect(mockSendRequest).toHaveBeenCalledWith(
      "validate_inputs",
      expect.objectContaining({ sample_map_xlsx: null, well_layout: null }),
    );
  });

  it("stores the finding the validation reported, and holds the run", async () => {
    // The sidecar reports the disagreement in `errors` as well, so either field
    // alone would disable Run here. Both are asserted because they cover
    // different moments: the error goes away on the next validation, the
    // finding survives until the workbook is replaced.
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: false,
      errors: ["expected: Fwd List and expected_mutations describe different plates"],
      plate_order: { ...REPORT, severity: "blocking" },
    });

    await store.validateInputs();

    expect(store.plateOrderFinding).not.toBeNull();
    expect(selectPlateOrderSeverity(store)).toBe("blocking");
    expect(selectCanRun(store)).toBe(false);
  });

  it("refuses an analyze while a finding stands, even with validation clean", async () => {
    // The path the 2026-08-04 incident took: picking the workbook stores the
    // finding on its own, and the operator can press Run without validating.
    const store = makeRunnableStore({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
      validationErrors: [],
    });

    expect(selectCanRun(store)).toBe(false);
  });

  it("keeps blocking after the operator names the sheet and column", async () => {
    // Naming the rows to read says nothing about which of the workbook's two
    // plates was pipetted, so it is not an answer to this and does not clear it.
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: false,
      errors: ["expected: Fwd List and expected_mutations describe different plates"],
      plate_order: { ...REPORT, severity: "blocking" },
    });
    await store.validateInputs();

    store.setVariantColumn("mutation");

    expect(selectPlateOrderSeverity(store)).toBe("blocking");
    expect(selectCanRun(store)).toBe(false);
  });

  it("reports nothing when the response carries no plate_order key", async () => {
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    expect(store.plateOrderFinding).toBeNull();
    expect(selectPlateOrderSeverity(store)).toBeNull();
    expect(selectCanRun(store)).toBe(true);
  });

  it("clears a previous finding when a later validation finds nothing", async () => {
    const store = makeRunnableStore({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    expect(store.plateOrderFinding).toBeNull();
  });

  it("checks the workbook alone when one is picked, not the whole input set", async () => {
    const store = makeStore({ expectedPath: "D:/project/KURO_expected.xlsx" });
    mockSendRequest.mockResolvedValueOnce(REPORT);

    await store.checkExpectedPlateOrder("D:/project/KURO_expected.xlsx");

    expect(mockSendRequest).toHaveBeenCalledTimes(1);
    expect(mockSendRequest).toHaveBeenCalledWith(
      "check_plate_order",
      { path: "D:/project/KURO_expected.xlsx" },
      expect.any(Number),
    );
    // The RPC answers without a severity; the slice grades it blocking, which is
    // what holds Run before any validation has been asked for.
    expect(store.plateOrderFinding?.severity).toBe("blocking");
    expect(selectCanRun(store)).toBe(false);
  });

  it("stays silent when the workbook agrees with itself", async () => {
    const store = makeStore({ expectedPath: "D:/project/KURO_expected.xlsx" });
    mockSendRequest.mockResolvedValueOnce({
      ...REPORT,
      mismatched: false,
      missing_from_expected: [],
    });

    await store.checkExpectedPlateOrder("D:/project/KURO_expected.xlsx");

    expect(store.plateOrderFinding).toBeNull();
  });

  it("stays silent when the check cannot run at all", async () => {
    // An older sidecar does not know the method. Inventing a problem there
    // would strand the operator on one that was never reported.
    const store = makeStore({ expectedPath: "D:/project/KURO_expected.xlsx" });
    mockSendRequest.mockRejectedValueOnce(new Error("unknown method"));

    await store.checkExpectedPlateOrder("D:/project/KURO_expected.xlsx");

    expect(store.plateOrderFinding).toBeNull();
  });

  it("drops the finding when another workbook is picked", () => {
    const store = makeRunnableStore({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });

    store.setExpectedPath("D:/project/other.xlsx");

    expect(store.plateOrderFinding).toBeNull();
    expect(selectCanRun(store)).toBe(true);
  });

  it("offers no way to build a well layout by hand", () => {
    // v0.15.6 removed the flow: nobody checked 96 rows, and analyze assigns the
    // wells on its own whether or not a layout was pinned.
    const store = makeRunnableStore();

    expect("buildWellLayout" in store).toBe(false);
    expect("confirmWellLayout" in store).toBe(false);
    expect("clearWellLayout" in store).toBe(false);
  });
});
