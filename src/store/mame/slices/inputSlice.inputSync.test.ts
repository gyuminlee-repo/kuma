/**
 * Inputs that reach the MAME store from more than one place.
 *
 * Item 14: the expected workbook can be chosen by Browse, by dropping it on the
 * window, from the missing-inputs banner, or by auto-fill. Only Browse asked the
 * two questions a new workbook owes (plate order, which sheet and column), so
 * the other routes ran with no plate-order gate and no mapping picker.
 * `chooseExpectedPath` is the one entry every route uses.
 *
 * Item 4: `cdsStart`/`cdsEnd` were overwritten by the longest ORF whenever the
 * asynchronous `parse_reference` answered, which lands after the restore and
 * after Step 1 Generate have set the bounds they mean.
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

const PLAIN_LIST_INFO = {
  is_kuro_export: false,
  sheets: ["Sheet1"],
  headers: { Sheet1: ["mutation"] },
  suggested_column: "mutation",
};

/** Two ORFs: the longest (0-900) and the gene the operator means (300-600). */
const PARSED_REFERENCE = {
  cds_candidates: [
    { start: 0, end: 900, source: "orf", aa_length: 299 },
    { start: 300, end: 600, source: "orf", aa_length: 99 },
  ],
  sequence_length: 1200,
  format: "fasta",
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

/** Resolve every pending microtask the store's fire-and-forget calls queued. */
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
}

describe("chooseExpectedPath: one entry for every route to the expected workbook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("asks about plate order and the variant source of the chosen file", async () => {
    mockSendRequest.mockImplementation((method: string) => {
      if (method === "inspect_variant_source") return Promise.resolve(PLAIN_LIST_INFO);
      if (method === "check_plate_order") return Promise.resolve({ comparable: false });
      return Promise.resolve({});
    });
    const store = makeStore();

    store.chooseExpectedPath("D:/project/variants.xlsx");
    await settle();

    const methods = mockSendRequest.mock.calls.map((c) => c[0]);
    expect(methods).toContain("check_plate_order");
    expect(methods).toContain("inspect_variant_source");
    expect(store.expectedPath).toBe("D:/project/variants.xlsx");
    expect(store.variantSourceInfo).toEqual(PLAIN_LIST_INFO);
    expect(store.variantColumn).toBe("mutation");
  });

  it("clears both findings when the path is emptied", async () => {
    const store = makeStore({ expectedPath: "D:/project/variants.xlsx" });
    store.chooseExpectedPath("");
    await settle();
    expect(mockSendRequest).not.toHaveBeenCalled();
    expect(store.expectedPath).toBe("");
    expect(store.plateOrderFinding).toBeNull();
    expect(store.variantSourceInfo).toBeNull();
  });
});

describe("CDS bounds are not overwritten by the reference parse", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockSendRequest.mockImplementation((method: string) =>
      Promise.resolve(method === "mame.ingest.parse_reference" ? PARSED_REFERENCE : {}),
    );
  });

  it("a new reference with no stated bounds takes the longest ORF", async () => {
    const store = makeStore();
    store.setReferencePath("D:/project/ref.fasta");
    await settle();
    expect(store.cdsStart).toBe(0);
    expect(store.cdsEnd).toBe(900);
    expect(store.selectedAnalyzeCdsIndex).toBe(0);
  });

  it("Generate's bounds survive the parse that answers after them", async () => {
    // BarcodeSetupPanel: setReferencePath(amplicon) then setParams(cds).
    const store = makeStore();
    store.setReferencePath("D:/project/design/amplicon.fa");
    store.setParams({ cdsStart: 300, cdsEnd: 600 });
    await settle();
    expect(store.cdsStart).toBe(300);
    expect(store.cdsEnd).toBe(600);
    expect(store.selectedAnalyzeCdsIndex).toBe(1);
  });

  it("an explicit choice that matches no candidate is kept and selects none", async () => {
    const store = makeStore();
    store.setReferencePath("D:/project/ref.fasta");
    store.setParams({ cdsStart: 12, cdsEnd: 99 });
    await settle();
    expect(store.cdsStart).toBe(12);
    expect(store.cdsEnd).toBe(99);
    expect(store.selectedAnalyzeCdsIndex).toBeNull();
  });

  it("picking another reference file lets the parse choose again", async () => {
    const store = makeStore();
    store.setReferencePath("D:/project/a.fasta");
    store.setParams({ cdsStart: 300, cdsEnd: 600 });
    await settle();
    store.setReferencePath("D:/project/b.fasta");
    await settle();
    expect(store.cdsStart).toBe(0);
    expect(store.cdsEnd).toBe(900);
  });
});
