/**
 * The plate-order gate, at the store layer.
 *
 * A KURO export writes the same plate on `Fwd List`/`Fwd Plate` and on
 * `expected_mutations`. When they disagree and MAME has to read wells off the
 * expected sheet's row order, every verdict lands on the wrong well and nothing
 * in the output says so (2026-08-04, 94 wells). These cover the three things
 * that have to hold for that to be caught: the finding is asked for and stored,
 * it is graded against the layout inputs actually sent, and a blocking grade
 * stops the run.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { selectCanRun, selectPlateOrderSeverity } from "../selectors";
import { createInputSlice } from "./inputSlice";

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
    setVerdicts: vi.fn(),
    setReplicates: vi.fn(),
    setSummary: vi.fn(),
    setAnalyzeYield: vi.fn(),
    setOutputPath: vi.fn(),
    setDistributionStats: vi.fn(),
    loadPlateData: vi.fn().mockResolvedValue(undefined),
    loadRunHealth: vi.fn().mockResolvedValue(undefined),
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

describe("mame inputSlice plate-order gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends the layout inputs with validate_inputs so the grade is the right one", async () => {
    // Omitting these grades every disagreement as blocking, including the ones
    // this run's own well coordinates make harmless.
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

  it("stores a blocking finding and stops the run", async () => {
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      // `valid` stays true by contract; the gate is this layer's job.
      valid: true,
      errors: [],
      plate_order: { ...REPORT, severity: "blocking" },
    });

    await store.validateInputs();

    expect(store.plateOrderFinding?.severity).toBe("blocking");
    expect(selectPlateOrderSeverity(store)).toBe("blocking");
    expect(selectCanRun(store)).toBe(false);
  });

  it("refuses an analyze started past the disabled button, and says why", async () => {
    const store = makeRunnableStore({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });

    await store.runAnalysis();

    expect(mockSendRequest).not.toHaveBeenCalled();
    expect(store.isAnalyzing).toBe(false);
    expect(store.validationErrors).toHaveLength(1);
    // Names the sheet, the disagreeing well and the mutant missing from the
    // expected sheet, so the operator knows which file to look at.
    expect(store.validationErrors[0]).toContain("Fwd List");
    expect(store.validationErrors[0]).toContain("A2");
    expect(store.validationErrors[0]).toContain("Q17R");
    expect(store.validationErrors[0]).toContain("KURO_expected.xlsx");
  });

  it("lets an info finding through: it is stated, not gated", async () => {
    const store = makeRunnableStore({ sampleMapPath: "D:/project/sample_map.xlsx" });
    mockSendRequest.mockResolvedValueOnce({
      valid: true,
      errors: [],
      plate_order: { ...REPORT, severity: "info" },
    });

    await store.validateInputs();

    expect(store.plateOrderFinding?.severity).toBe("info");
    expect(selectPlateOrderSeverity(store)).toBe("info");
    expect(selectCanRun(store)).toBe(true);
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
    // The RPC answers without a severity; the slice grades it as the sidecar would.
    expect(store.plateOrderFinding?.severity).toBe("blocking");
  });

  it("grades a picked workbook as info when the wells come from elsewhere", async () => {
    const store = makeStore({
      expectedPath: "D:/project/KURO_expected.xlsx",
      sampleMapPath: "D:/project/sample_map.xlsx",
    });
    mockSendRequest.mockResolvedValueOnce(REPORT);

    await store.checkExpectedPlateOrder("D:/project/KURO_expected.xlsx");

    expect(store.plateOrderFinding?.severity).toBe("info");
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
    // An older sidecar does not know the method. Inventing a block there would
    // strand the operator on a problem that was never reported.
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

  it("lifts the gate once the operator states the well layout", async () => {
    // The way out is to say which sample sits in which well, which is exactly
    // what makes the sheet order irrelevant to the run. Re-graded without a
    // second round-trip.
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: true,
      errors: [],
      plate_order: { ...REPORT, severity: "blocking" },
    });
    await store.validateInputs();
    expect(selectCanRun(store)).toBe(false);

    store.confirmWellLayout([{ well: "A1", sample: "K53I" }]);

    expect(selectPlateOrderSeverity(store)).toBe("info");
    expect(selectCanRun(store)).toBe(true);
  });
});
