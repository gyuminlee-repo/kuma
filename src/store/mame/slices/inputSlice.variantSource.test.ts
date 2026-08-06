/**
 * Reading a plain variant list, and writing the Janus pick list, at the store
 * layer.
 *
 * Two facts this covers, both of which are silent when they go wrong:
 *   - the sheet and column the operator picked have to reach every call that
 *     reads that file. If the validation and the run read different columns,
 *     the run is validated against rows nobody looked at.
 *   - the analyze run writes the pick list itself (the instrument mapping is
 *     written only by a manual export, not covered here). The sidecar no
 *     longer refuses over a blank liquid class, but the operator's settings
 *     (volume above all) still have to reach the call that writes it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createInputSlice } from "./inputSlice";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

const PLAIN_LIST_INFO = {
  is_kuro_export: false,
  sheets: ["Sheet1", "Notes"],
  headers: { Sheet1: ["no", "mutation", "note"], Notes: ["free text"] },
  suggested_column: "mutation",
};

const KURO_INFO = {
  is_kuro_export: true,
  sheets: ["expected_mutations", "Fwd List"],
  headers: { expected_mutations: ["mutant_id", "status"], "Fwd List": ["well"] },
  suggested_column: "mutant_id",
};

const ANALYZE_REPLY = {
  verdicts: [],
  replicates: [],
  summary: {},
  output_path: "D:/project/result.xlsx",
  distribution_stats: null,
  janus_autosave: {
    status: "saved",
    output_path: "D:/project/result_picks.csv",
    format: "csv",
    row_count: 12,
    excluded: [],
    excluded_count: 0,
    errors: [],
    warnings: [],
  },
};

/**
 * A store whose inputs are already chosen, so each test only sets up the one
 * thing it is about.
 *
 * `createInputSlice` carries its own initial state (empty paths, `raw_run`
 * mode), and that state lands on the object after the seed does. So the seed
 * has to be applied a second time, after the slice: assigning it only before
 * leaves every path empty and the mode `raw_run`, which sends `runAnalysis`
 * down the demux branch and out through its missing-input guard before any RPC
 * is issued.
 */
function makeStore(initial: Partial<AppState> = {}) {
  const seed: Partial<AppState> = {
    inputDir: "D:/project/consensus",
    expectedPath: "D:/project/variants.xlsx",
    referencePath: "D:/project/ref.fasta",
    outputPath: "D:/project",
    inputMode: "consensus" as const,
    ...initial,
  };
  const state: Partial<AppState> = {
    setVerdicts: vi.fn(),
    setReplicates: vi.fn(),
    setSummary: vi.fn(),
    setAnalyzeYield: vi.fn(),
    setOutputPath: vi.fn(),
    setDistributionStats: vi.fn(),
    loadPlateData: vi.fn().mockResolvedValue(undefined),
    loadRunHealth: vi.fn().mockResolvedValue(undefined),
    ...seed,
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
  Object.assign(state, slice, seed);
  return state as AppState;
}

describe("mame inputSlice variant source", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("preselects the auto-detected column so the shown mapping is the one that runs", async () => {
    const store = makeStore();
    mockSendRequest.mockResolvedValueOnce(PLAIN_LIST_INFO);

    await store.inspectVariantSource("D:/project/variants.xlsx");

    expect(store.variantSourceInfo).toEqual(PLAIN_LIST_INFO);
    expect(store.variantSheet).toBe("Sheet1");
    expect(store.variantColumn).toBe("mutation");
    // A preselected suggestion is not the operator speaking.
    expect(store.variantSelectionExplicit).toBe(false);
  });

  it("names no sheet or column for a KURO export", async () => {
    // Its reader knows both, and sending them would be a second way to say the
    // same thing. The panel hides itself off `is_kuro_export`.
    const store = makeStore({ expectedPath: "D:/project/kuro.xlsx" });
    mockSendRequest.mockResolvedValueOnce(KURO_INFO);

    await store.inspectVariantSource("D:/project/kuro.xlsx");

    expect(store.variantSourceInfo?.is_kuro_export).toBe(true);
    expect(store.variantSheet).toBeNull();
    expect(store.variantColumn).toBeNull();
  });

  it("keeps quiet when the sidecar does not know the method", async () => {
    const store = makeStore();
    mockSendRequest.mockRejectedValueOnce(new Error("unknown method"));

    await store.inspectVariantSource("D:/project/variants.xlsx");

    expect(store.variantSourceInfo).toBeNull();
  });

  it("forgets the mapping when another file is picked", () => {
    const store = makeStore({
      variantSourceInfo: PLAIN_LIST_INFO,
      variantSheet: "Sheet1",
      variantColumn: "mutation",
      variantSelectionExplicit: true,
    });

    store.setExpectedPath("D:/project/other.xlsx");

    expect(store.variantSourceInfo).toBeNull();
    expect(store.variantSheet).toBeNull();
    expect(store.variantColumn).toBeNull();
    expect(store.variantSelectionExplicit).toBe(false);
  });

  it("drops the column when the sheet changes: the headers are not the same", () => {
    const store = makeStore({
      variantSourceInfo: PLAIN_LIST_INFO,
      variantSheet: "Sheet1",
      variantColumn: "mutation",
    });

    store.setVariantSheet("Notes");

    expect(store.variantColumn).toBeNull();
    expect(store.variantSelectionExplicit).toBe(true);
  });

  it("sends the same sheet and column to validate_inputs and to both analyze paths", async () => {
    const chosen = { variant_sheet: "Sheet1", variant_column: "mutation" };

    const consensus = makeStore({
      variantSheet: "Sheet1",
      variantColumn: "mutation",
    });
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });
    await consensus.validateInputs();
    expect(mockSendRequest).toHaveBeenLastCalledWith(
      "validate_inputs",
      expect.objectContaining(chosen),
    );

    mockSendRequest.mockResolvedValueOnce(ANALYZE_REPLY);
    await consensus.runAnalysis();
    expect(mockSendRequest).toHaveBeenLastCalledWith(
      "analyze",
      expect.objectContaining(chosen),
      expect.any(Number),
    );

    const rawRun = makeStore({
      variantSheet: "Sheet1",
      variantColumn: "mutation",
      inputMode: "raw_run",
      rawRunParams: { ...consensus.rawRunParams, customBarcodesPath: "D:/bc.xlsx" },
    });
    mockSendRequest.mockResolvedValueOnce(ANALYZE_REPLY);
    await rawRun._demuxAndAnalyze(null);
    expect(mockSendRequest).toHaveBeenLastCalledWith(
      "analyze",
      expect.objectContaining(chosen),
      expect.any(Number),
    );
  });

  it("omits both params while nothing is chosen, which is the old behaviour", async () => {
    const store = makeStore();
    mockSendRequest.mockResolvedValueOnce({ valid: true, errors: [] });

    await store.validateInputs();

    const params = mockSendRequest.mock.calls[0][1] as Record<string, unknown>;
    expect(params).not.toHaveProperty("variant_sheet");
    expect(params).not.toHaveProperty("variant_column");
  });

  it("carries the Janus settings into the analyze call", async () => {
    const store = makeStore();
    store.setJanusSettings({ ...store.janusSettings, liquidClass: "Cells_100" });
    mockSendRequest.mockResolvedValueOnce(ANALYZE_REPLY);

    await store.runAnalysis();

    const params = mockSendRequest.mock.calls[0][1] as {
      janus_settings: Record<string, unknown>;
    };
    expect(params.janus_settings.liquid_class).toBe("Cells_100");
    expect(params.janus_settings.output_schema).toBe("device9");
  });

  it("keeps what became of that mapping instead of dropping it", async () => {
    const store = makeStore();
    mockSendRequest.mockResolvedValueOnce(ANALYZE_REPLY);

    await store.runAnalysis();

    expect(store.janusAutosave?.status).toBe("saved");
    expect(store.janusAutosave?.row_count).toBe(12);
  });
});
