/**
 * designSlice.resultLoss.test.ts, a finished design has to survive its own
 * success path, and every way the run can end has to leave something behind.
 *
 * Regression: a user ran 95 mutations, the sidecar designed all 95, and the
 * app showed an empty step 5. The post-design EVOLVEpro reload
 * (`loadEvolveproCsv` without `preserveDesignResults`) rewrote `mutationText`
 * with the un-doubled top-N selection, `buildKuroDesignInputPatch` read that as
 * a design-input change, and the reset patch wiped the results two statements
 * after they were stored. The autosave written afterwards showed
 * designResults 0 / totalCount 0 with rescuedMutations still populated, which
 * is the fingerprint of that reset patch rather than of a design that failed.
 *
 * The reload has to return a different variant list for the two calls, because
 * that difference is the trigger: the first call asks for `sendCount * 2`
 * variants and the second for `maxPrimers`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  sendRequest: vi.fn(),
  notifyJobError: vi.fn(),
  notifyJobDone: vi.fn(),
  toast: { info: vi.fn(), warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("../../lib/toast", () => ({
  notifyJobError: mocks.notifyJobError,
  notifyJobDone: mocks.notifyJobDone,
  notifyJobStarted: vi.fn(),
}));

vi.mock("../../lib/notify", () => ({
  notifyJobComplete: vi.fn(),
}));

import { useAppStore } from "../appStore";
import type { SdmPrimerResult } from "../../types/models";

const POOL = ["V1A", "V2A", "V3A", "V4A"];

function primer(mutation: string): SdmPrimerResult {
  return {
    mutation,
    aa_position: 1,
    codon_pos: 0,
    forward_seq: "ATGC",
    reverse_seq: "GCAT",
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    candidate_fwd_count: 1,
    candidate_rev_count: 1,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 4,
    has_offtarget: false,
    penalty: 0,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "ATG",
    mt_codon: "GCG",
    overlap_seq: "ATGC",
    warnings: [],
  };
}

/** EVOLVEpro reload answer: the selection shrinks with the requested top-N. */
function evolveproResponse(params: Record<string, unknown>) {
  const topN = typeof params.top_n === "number" ? params.top_n : POOL.length;
  const variants = POOL.slice(0, Math.min(topN, POOL.length));
  return {
    variants,
    y_preds: variants.map((_, i) => 1 - i * 0.1),
    total_count: POOL.length,
    selected_count: variants.length,
    pool_variants: POOL,
    ranked_candidates: POOL.map((variant, i) => ({ variant, y_pred: 1 - i * 0.1 })),
  };
}

/** The design answer: every intended mutation designed, nothing failed. */
function designResponse(mutations: string[]) {
  return {
    results: mutations.map(primer),
    success_count: mutations.length,
    total_count: mutations.length,
    failed_mutations: [],
    rescue_stats: {
      pool_cascade: 0,
      auto_relax: 0,
      positions_attempted: 0,
      pool_variants_tried: 0,
    },
    rescued_mutations: [],
  };
}

function seedWorkspace() {
  useAppStore.setState({
    fastaPath: "/tmp/template.dna",
    selectedGene: "267",
    mutationInputMode: "evolvepro",
    mutationText: POOL.join("\n"),
    evolveproCsvPath: "/tmp/pool.csv",
    evolveproMode: "pipeline",
    evolveproSelectedVariants: [...POOL],
    evolveproRankedCandidates: POOL.map((variant, i) => ({ variant, y_pred: 1 - i * 0.1 })),
    poolVariants: [...POOL],
    fillOnFailure: true,
    maxPrimers: 2,
    isDesigning: false,
    lastDesignRun: null,
  } as never);
}

beforeEach(() => {
  seedWorkspace();
  mocks.sendRequest.mockReset();
  mocks.notifyJobError.mockReset();
  mocks.notifyJobDone.mockReset();
});

afterEach(() => {
  useAppStore.getState().cancelDiversityReload();
  useAppStore.setState({
    ...useAppStore.getState(),
    designResults: [],
    lastDesignRun: null,
    isDesigning: false,
  } as never);
});

describe("a successful design survives the post-design EVOLVEpro reload", () => {
  it("keeps the designed primers and the counters the sidecar produced", async () => {
    mocks.sendRequest.mockImplementation(
      async (method: string, params: Record<string, unknown>) => {
        if (method === "load_evolvepro_csv") return evolveproResponse(params);
        if (method === "design_sdm_primers") {
          const text = String(params.mutations_csv_or_text ?? "");
          return designResponse(text.split("\n").filter(Boolean).slice(0, 2));
        }
        throw new Error(`unexpected method ${method}`);
      },
    );

    await useAppStore.getState().designPrimers();

    const state = useAppStore.getState();
    expect(state.designResults.map((r) => r.mutation)).toEqual(["V1A", "V2A"]);
    expect(state.successCount).toBe(2);
    // totalCount is the intended-mutation count, never 0 after a design that
    // returned results. 0 here was the shape the user's autosave carried.
    expect(state.totalCount).toBe(2);
    expect(state.lastDesignRun?.outcome).toBe("success");
    expect(state.lastDesignRun?.successCount).toBe(2);
    expect(state.isDesigning).toBe(false);
  });

  it("re-runs the EVOLVEpro reload with the result-preserving flag", async () => {
    mocks.sendRequest.mockImplementation(
      async (method: string, params: Record<string, unknown>) => {
        if (method === "load_evolvepro_csv") return evolveproResponse(params);
        if (method === "design_sdm_primers") {
          const text = String(params.mutations_csv_or_text ?? "");
          return designResponse(text.split("\n").filter(Boolean).slice(0, 2));
        }
        throw new Error(`unexpected method ${method}`);
      },
    );

    await useAppStore.getState().designPrimers();

    // The selection was re-derived (mutationText follows the reload), and the
    // results still stand next to it.
    expect(useAppStore.getState().mutationText).toBe("V1A\nV2A");
    expect(useAppStore.getState().designResults).toHaveLength(2);
  });
});

describe("every way a design run can end leaves a trace", () => {
  function textModeWorkspace() {
    useAppStore.setState({
      mutationInputMode: "text",
      mutationText: "V1A\nV2A",
      evolveproCsvPath: "",
      evolveproSelectedVariants: [],
      evolveproRankedCandidates: [],
      fillOnFailure: false,
      lastDesignRun: null,
    } as never);
  }

  beforeEach(textModeWorkspace);

  it("success: status line, toast, and a success record", async () => {
    mocks.sendRequest.mockResolvedValue(designResponse(["V1A", "V2A"]));

    await useAppStore.getState().designPrimers();

    const state = useAppStore.getState();
    expect(state.statusMessage).toContain("2/2 designed");
    expect(state.lastDesignRun?.outcome).toBe("success");
    expect(mocks.notifyJobDone).toHaveBeenCalled();
  });

  it("failure: status line, error toast, and a failed record", async () => {
    mocks.sendRequest.mockRejectedValue(new Error("primer3 exploded"));

    await useAppStore.getState().designPrimers();

    const state = useAppStore.getState();
    expect(state.statusMessage).toContain("Design failed");
    expect(state.lastDesignRun?.outcome).toBe("failed");
    expect(state.lastDesignRun?.detail).toContain("primer3 exploded");
    expect(mocks.notifyJobError).toHaveBeenCalled();
    expect(state.isDesigning).toBe(false);
  });

  it("cancel: status line and a cancelled record, no error toast", async () => {
    mocks.sendRequest.mockResolvedValue({ cancelled: true });

    await useAppStore.getState().designPrimers();

    const state = useAppStore.getState();
    expect(state.statusMessage).toContain("cancel");
    expect(state.lastDesignRun?.outcome).toBe("cancelled");
    // The user asked for this one, so it does not get a red toast.
    expect(mocks.notifyJobError).not.toHaveBeenCalled();
    expect(state.isDesigning).toBe(false);
  });

  it("sidecar loss: no longer returns in silence", async () => {
    mocks.sendRequest.mockRejectedValue(new Error("Sidecar killed"));

    await useAppStore.getState().designPrimers();

    const state = useAppStore.getState();
    // The old code returned here without writing anything, so the user saw the
    // pre-run status line and an empty table with no explanation.
    expect(state.statusMessage).toContain("interrupted");
    expect(state.lastDesignRun?.outcome).toBe("interrupted");
    expect(mocks.notifyJobError).toHaveBeenCalledWith(
      "Design interrupted",
      expect.stringContaining("sidecar"),
    );
    expect(state.isDesigning).toBe(false);
  });
});

describe("a design run belongs to the workspace that started it", () => {
  function textModeWorkspace() {
    useAppStore.setState({
      mutationInputMode: "text",
      mutationText: "V1A\nV2A",
      evolveproCsvPath: "",
      evolveproSelectedVariants: [],
      evolveproRankedCandidates: [],
      fillOnFailure: false,
      lastDesignRun: null,
    } as never);
  }
  beforeEach(textModeWorkspace);

  function pendingDesigns() {
    const releases: Array<(value: unknown) => void> = [];
    mocks.sendRequest.mockImplementation((method: string) =>
      method === "design_sdm_primers"
        ? new Promise((resolve) => { releases.push(resolve); })
        : Promise.resolve({}));
    return releases;
  }

  it("Clear All cancels the running design and its late reply does not refill the table", async () => {
    const releases = pendingDesigns();
    const run = useAppStore.getState().designPrimers();
    await vi.waitFor(() => expect(releases).toHaveLength(1));

    useAppStore.getState().resetAll();
    expect(mocks.sendRequest).toHaveBeenCalledWith("cancel_design", {});
    expect(useAppStore.getState().statusMessage).toMatch(/cancel/i);

    releases[0](designResponse(["V1A", "V2A"]));
    await run;

    const state = useAppStore.getState();
    expect(state.designResults).toEqual([]);
    expect(state.successCount).toBe(0);
    expect(state.lastDesignRun).toBeNull();
    expect(state.backendDesignStateSynced).toBe(false);
    expect(state.isDesigning).toBe(false);
  });

  it("an older run neither overwrites nor ends the run started after a reset", async () => {
    const releases = pendingDesigns();
    const old = useAppStore.getState().designPrimers();
    await vi.waitFor(() => expect(releases).toHaveLength(1));
    useAppStore.getState().resetAll();
    seedWorkspace();
    textModeWorkspace();
    useAppStore.setState({ mutationText: "V3A" } as never);
    const current = useAppStore.getState().designPrimers();
    await vi.waitFor(() => expect(releases).toHaveLength(2));

    releases[0](designResponse(["V1A", "V2A"]));
    await old;
    expect(useAppStore.getState().isDesigning).toBe(true);
    expect(useAppStore.getState().designResults).toEqual([]);

    releases[1](designResponse(["V3A"]));
    await current;
    expect(useAppStore.getState().designResults.map((r) => r.mutation)).toEqual(["V3A"]);
    expect(useAppStore.getState().isDesigning).toBe(false);
  });

  it("keeps the results when a background lookup resets design inputs mid-run", async () => {
    const releases = pendingDesigns();
    const run = useAppStore.getState().designPrimers();
    await vi.waitFor(() => expect(releases).toHaveLength(1));

    // What a domain or BLAST lookup finishing during the run does: it rewrites a
    // design input through buildKuroDesignInputPatch, which empties the table.
    useAppStore.getState().setDomainStrategy("equal");

    releases[0](designResponse(["V1A", "V2A"]));
    await run;
    const state = useAppStore.getState();
    expect(state.designResults.map((r) => r.mutation)).toEqual(["V1A", "V2A"]);
    expect(state.lastDesignRun?.outcome).toBe("success");
    expect(state.isDesigning).toBe(false);
    // Kept, and marked: the user is told these are for the inputs it began with.
    expect(mocks.toast.warning).toHaveBeenCalledTimes(1);
  });

  it("does not mark a run whose inputs stayed put", async () => {
    const releases = pendingDesigns();
    mocks.toast.warning.mockClear();
    const run = useAppStore.getState().designPrimers();
    await vi.waitFor(() => expect(releases).toHaveLength(1));
    releases[0](designResponse(["V1A", "V2A"]));
    await run;
    expect(mocks.toast.warning).not.toHaveBeenCalled();
  });

  it("drops a retry reply that lands after a reset", async () => {
    let release!: (value: unknown) => void;
    mocks.sendRequest.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    const retry = useAppStore.getState().retryFailedMutation("V1A", {});
    await vi.waitFor(() => expect(mocks.sendRequest).toHaveBeenCalled());
    useAppStore.getState().resetAll();
    release({ candidates: [primer("V1A")] });

    await expect(retry).resolves.toEqual([]);
    expect(useAppStore.getState().alternativesCache).toEqual({});
  });
});
