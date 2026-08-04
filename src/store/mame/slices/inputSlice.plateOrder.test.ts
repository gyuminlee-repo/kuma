/**
 * The plate-order finding, at the store layer.
 *
 * A KURO export writes the same plate on `Fwd List`/`Fwd Plate` and on
 * `expected_mutations`. When they disagree and MAME reads wells off the
 * expected sheet's row order, every verdict lands on the wrong well and nothing
 * in the output says so (2026-08-04, 94 wells).
 *
 * v0.15.6 changed what follows from that. The operator now names the sheet and
 * the column the variant list is read from, so the disagreement is reported and
 * the run proceeds: refusing would be the program overruling a statement it
 * asked for. These cover that the finding is still asked for and stored, that
 * it no longer stops anything, and that it goes quiet once the operator has
 * pointed at the rows themselves.
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

  it("stores a finding the sidecar graded blocking, and still lets the run start", async () => {
    // The backend keeps its own grading vocabulary; the frontend stopped acting
    // on it. Nothing about a disagreeing workbook disables Run any more.
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: true,
      errors: [],
      plate_order: { ...REPORT, severity: "blocking" },
    });

    await store.validateInputs();

    expect(store.plateOrderFinding).not.toBeNull();
    expect(selectPlateOrderSeverity(store)).toBe("info");
    expect(selectCanRun(store)).toBe(true);
  });

  it("runs an analyze with a disagreeing workbook instead of refusing it", async () => {
    const store = makeRunnableStore({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });
    mockSendRequest.mockResolvedValueOnce({
      verdicts: [],
      replicates: [],
      summary: {},
      output_path: "D:/project/result.xlsx",
      distribution_stats: null,
    });

    await store.runAnalysis();

    expect(mockSendRequest).toHaveBeenCalledWith(
      "analyze",
      expect.anything(),
      expect.any(Number),
    );
    expect(store.validationErrors).toEqual([]);
  });

  it("says nothing at all once the operator named the sheet and column", async () => {
    // Their statement about which rows to read is the answer to the question
    // the notice would ask. Repeating it back adds nothing.
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: true,
      errors: [],
      plate_order: { ...REPORT, severity: "blocking" },
    });
    await store.validateInputs();
    expect(selectPlateOrderSeverity(store)).toBe("info");

    store.setVariantColumn("mutation");

    expect(selectPlateOrderSeverity(store)).toBeNull();
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
      plateOrderFinding: { ...REPORT, severity: "info" },
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
    // The RPC answers without a severity; the slice states it as information.
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
    // An older sidecar does not know the method. Inventing a problem there
    // would strand the operator on one that was never reported.
    const store = makeStore({ expectedPath: "D:/project/KURO_expected.xlsx" });
    mockSendRequest.mockRejectedValueOnce(new Error("unknown method"));

    await store.checkExpectedPlateOrder("D:/project/KURO_expected.xlsx");

    expect(store.plateOrderFinding).toBeNull();
  });

  it("drops the finding when another workbook is picked", () => {
    const store = makeRunnableStore({
      plateOrderFinding: { ...REPORT, severity: "info" },
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
