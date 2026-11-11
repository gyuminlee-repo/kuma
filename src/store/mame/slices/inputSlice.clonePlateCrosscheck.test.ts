/**
 * The clone-plate crosscheck, at the store layer: stored and never gating.
 *
 * KURO gives each primer its well by design-sheet index and the run fills the
 * clone plate by residue position, so the two name different clones in the same
 * well on any export not already written in position order. That is the normal
 * state of most real workbooks rather than a fault in one, and which of the two
 * describes the tubes in the rack is written in no input on the screen.
 *
 * So the one thing these pin above all others is that the finding does not reach
 * `selectCanRun`. A reportable value routed through the plate-order fields would
 * weaken a refusal that exists for a different reason, and a reportable value
 * wired into the Run button would refuse nearly every analyse run.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { selectCanRun } from "../selectors";
import { createInputSlice } from "./inputSlice";
import { createAnalysisSliceDoubles } from "./testHelpers/analysisSliceDoubles";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

/** The payload the sidecar sends, which it sends only on a mismatch. */
const CROSSCHECK = {
  status: "mismatch",
  plate_sheet: "Fwd List",
  wells_compared: 95,
  mismatch_count: 87,
  examples: [
    { well: "A1", primer_plate: "S22T", clone_plate: "S11I" },
    { well: "B1", primer_plate: "S11I", clone_plate: "S22T" },
  ],
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

describe("mame inputSlice clone-plate crosscheck", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not hold the run while a disagreement stands", () => {
    const store = makeRunnableStore({ clonePlateCrosscheck: CROSSCHECK });

    expect(selectCanRun(store)).toBe(true);
  });

  it("stores what the validation reported and still allows the run", async () => {
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: true,
      errors: [],
      clone_plate_crosscheck: CROSSCHECK,
    });

    await store.validateInputs();

    expect(store.clonePlateCrosscheck).toEqual(CROSSCHECK);
    expect(store.validationErrors).toEqual([]);
    expect(store.plateOrderFinding).toBeNull();
    expect(selectCanRun(store)).toBe(true);
  });

  it("clears the finding when the response carries none", async () => {
    // Absent means nothing to show. A notice left standing would name wells of
    // a workbook that is no longer selected.
    const store = makeRunnableStore({ clonePlateCrosscheck: CROSSCHECK });
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    expect(store.clonePlateCrosscheck).toBeNull();
  });

  it("clears the finding when another workbook is picked", () => {
    const store = makeRunnableStore({ clonePlateCrosscheck: CROSSCHECK });

    store.setExpectedPath("D:/project/other.xlsx");

    expect(store.clonePlateCrosscheck).toBeNull();
  });

  // Every one of these is an analyze input: the sheet and the column decide
  // which rows are read, and the placement decides the control well and where
  // every occupant after it sits. A finding measured on the previous value
  // names wells of a comparison that no longer describes the inputs, and the
  // operator reads it as a verdict on the ones now on screen.
  it("clears the finding when another sheet is picked", () => {
    const store = makeRunnableStore({
      clonePlateCrosscheck: CROSSCHECK,
      variantSheet: "Sheet1",
    });

    store.setVariantSheet("Sheet2");

    expect(store.clonePlateCrosscheck).toBeNull();
  });

  it("clears the finding when another variant column is picked", () => {
    const store = makeRunnableStore({
      clonePlateCrosscheck: CROSSCHECK,
      variantColumn: "mutation",
    });

    store.setVariantColumn("mutant_id");

    expect(store.clonePlateCrosscheck).toBeNull();
  });

  it("clears the finding when the control placement changes", () => {
    const store = makeRunnableStore({
      clonePlateCrosscheck: CROSSCHECK,
      wtPlacement: "last_well",
    });

    store.setWtPlacement("after_last_variant");

    expect(store.clonePlateCrosscheck).toBeNull();
  });

  it("clears the finding when the validation itself fails", async () => {
    // The success path clears on an absent key. A refused call never gets that
    // far, so the catch has to clear it too, or a finding from the previous
    // attempt stands beside "Validation failed" as though it were this one.
    const store = makeRunnableStore({ clonePlateCrosscheck: CROSSCHECK });
    mockSendRequest.mockRejectedValueOnce(new Error("sidecar is gone"));

    await store.validateInputs();

    expect(store.clonePlateCrosscheck).toBeNull();
    expect(store.validationErrors.length).toBeGreaterThan(0);
  });

  it("leaves the plate-order refusal exactly as it was", async () => {
    // The two findings travel on the same response and are graded opposite
    // ways. The reportable one must not soften the blocking one.
    const store = makeRunnableStore();
    mockSendRequest.mockResolvedValueOnce({
      valid: false,
      errors: ["expected: Fwd List and expected_mutations describe different plates"],
      plate_order: {
        comparable: true,
        mismatched: true,
        plate_sheet: "Fwd List",
        examples: [{ well: "A2", plate: "K53I", expected: "I92D" }],
        missing_from_expected: [],
        absent_from_plate: [],
        severity: "blocking" as const,
      },
      clone_plate_crosscheck: CROSSCHECK,
    });

    await store.validateInputs();

    expect(store.clonePlateCrosscheck).toEqual(CROSSCHECK);
    expect(store.plateOrderFinding).not.toBeNull();
    expect(selectCanRun(store)).toBe(false);
  });
});
