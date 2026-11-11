/**
 * Which stored findings follow the inputs, and which two deliberately do not.
 *
 * Four of the fields `validate_inputs` fills are statements about one set of
 * inputs rather than about the files alone. Leave one standing past a change to
 * those inputs and it reads as the answer for the inputs now on screen, which
 * is the fault AGENTS.md states the rule for: changing an analyze input clears
 * the previous run outputs.
 *
 * `clonePlateCrosscheck` and `legacySampleMapFinding` are both measured against
 * the draft layout the expected rows produce, so the sheet, the column, the
 * control placement and the workbook itself all invalidate them.
 * `legacySampleMapFinding` reporting `differs` reaches `errors` and holds the
 * run, which makes a stale `differs` harmless; a stale `matches` is the case
 * this pins, because it tells the operator the hand-written map agrees with a
 * plate that was never drafted.
 *
 * The other two are pinned here as NEGATIVE cases, so the asymmetry cannot be
 * read as an omission and quietly "fixed".
 *
 * `plateOrderFinding` is blocking and `checkExpectedPlateOrder` sends the path
 * alone, so none of these setters changes what it would answer. Clearing it
 * would not invalidate a stale answer, it would release a refusal that the
 * setter has no way to re-establish.
 *
 * `barcodeAxisCounts` is not downstream of these inputs at all:
 * `_barcode_axis_counts` reads the custom barcode workbook on its own, and the
 * path it comes from lives in `rawRunParams`, which `setParams` already clears.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createInputSlice } from "./inputSlice";
import { createAnalysisSliceDoubles } from "./testHelpers/analysisSliceDoubles";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

/** An agreeing legacy map, which is the reading a stale value falsifies. */
const LEGACY = {
  path: "D:/project/sample_map.xlsx",
  status: "matches" as const,
  differences: [],
  wells_compared: 95,
};

const PLATE_ORDER = {
  comparable: true,
  mismatched: true,
  plate_sheet: "Fwd List",
  examples: [{ well: "A2", plate: "K53I", expected: "I92D" }],
  missing_from_expected: [],
  absent_from_plate: [],
  severity: "blocking" as const,
};

const AXES = { forward_count: 12, reverse_count: 8, wells: 96 };

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

function stored(initial: Partial<AppState> = {}) {
  return makeStore({
    inputDir: "D:/project/consensus",
    expectedPath: "D:/project/KURO_expected.xlsx",
    referencePath: "D:/project/ref.fasta",
    outputPath: "D:/project",
    inputMode: "consensus",
    legacySampleMapFinding: LEGACY,
    ...initial,
  });
}

describe("the legacy sample map finding follows the rows it was compared with", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clears when another sheet is picked", () => {
    const store = stored({ variantSheet: "Sheet1" });

    store.setVariantSheet("Sheet2");

    expect(store.legacySampleMapFinding).toBeNull();
  });

  it("clears when another variant column is picked", () => {
    const store = stored({ variantColumn: "mutation" });

    store.setVariantColumn("mutant_id");

    expect(store.legacySampleMapFinding).toBeNull();
  });

  it("clears when the control placement changes", () => {
    const store = stored({ wtPlacement: "last_well" });

    store.setWtPlacement("after_last_variant");

    expect(store.legacySampleMapFinding).toBeNull();
  });

  it("clears when another workbook is picked", () => {
    const store = stored();

    store.setExpectedPath("D:/project/other.xlsx");

    expect(store.legacySampleMapFinding).toBeNull();
  });

  it("clears when the validation itself fails", async () => {
    const store = stored();
    mockSendRequest.mockRejectedValueOnce(new Error("sidecar is gone"));

    await store.validateInputs();

    expect(store.legacySampleMapFinding).toBeNull();
    expect(store.validationErrors.length).toBeGreaterThan(0);
  });
});

describe("the two fields these setters must not clear", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the plate-order refusal, which no setter here can re-check", () => {
    const store = stored({
      variantSheet: "Sheet1",
      plateOrderFinding: PLATE_ORDER,
    });

    store.setVariantSheet("Sheet2");

    expect(store.plateOrderFinding).toEqual(PLATE_ORDER);
  });

  it("keeps the plate-order refusal when a validation fails", async () => {
    const store = stored({ plateOrderFinding: PLATE_ORDER });
    mockSendRequest.mockRejectedValueOnce(new Error("sidecar is gone"));

    await store.validateInputs();

    expect(store.plateOrderFinding).toEqual(PLATE_ORDER);
  });

  it("keeps the barcode axis counts, which describe another file entirely", () => {
    const store = stored({
      variantSheet: "Sheet1",
      barcodeAxisCounts: AXES,
    });

    store.setVariantSheet("Sheet2");
    store.setWtPlacement("after_last_variant");

    expect(store.barcodeAxisCounts).toEqual(AXES);
  });
});
