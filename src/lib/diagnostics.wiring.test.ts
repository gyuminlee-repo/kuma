/**
 * diagnostics.wiring.test.ts, the run section has to come from a real design
 * run rather than from hand-seeded store fields.
 *
 * diagnostics.test.ts seeds `lastDesignRequest` directly, so it would stay
 * green if designPrimers stopped recording the snapshot altogether. This file
 * drives designPrimers with a mocked sidecar, lets it store what it stores, and
 * reads the bundle out the other end. It also pins the two restore paths, which
 * carry failures back from disk without a request behind them.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  sendRequest: vi.fn(),
  toast: { info: vi.fn(), warning: vi.fn(), success: vi.fn(), error: vi.fn() },
  save: vi.fn(async () => "diagnostics-out.json"),
  writeTextFile: vi.fn(async (_path: string, _contents: string) => undefined),
}));

vi.mock("sonner", () => ({ toast: mocks.toast }));
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("../lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("./ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: mocks.save }));
vi.mock("@tauri-apps/plugin-fs", () => ({ writeTextFile: mocks.writeTextFile }));
vi.mock("@/lib/notify", () => ({ notifyJobComplete: vi.fn() }));
vi.mock("./notify", () => ({ notifyJobComplete: vi.fn() }));

import { generateDiagnosticsBundle, type DiagnosticsBundle } from "./diagnostics";
import { useAppStore } from "@/store/appStore";
import { applyKuroSnapshot } from "@/hooks/useAutosaveHydration";
import type { AutosaveSnapshot } from "@/lib/autosave";
import type { WorkspaceData } from "@/types/models";

const FAILURE_REASON =
  "No valid primer pair - reverse: closest Tm 71.1C at 19 bp, outside 58+-4.0C (length 19-27 bp)";

const SECRET_FASTA = "D:\\lab\\secret-campaign\\pET28a_target.dna";

const pristine = useAppStore.getState();

beforeEach(() => {
  mocks.sendRequest.mockReset();
  mocks.save.mockClear();
  mocks.writeTextFile.mockClear();
  localStorage.clear();
  useAppStore.setState({
    fastaPath: SECRET_FASTA,
    selectedGene: "267",
    mutationInputMode: "text",
    mutationText: "K182N\nF385Y",
    evolveproCsvPath: "",
    evolveproSelectedVariants: [],
    evolveproRankedCandidates: [],
    fillOnFailure: false,
    maxPrimers: 95,
    isDesigning: false,
    selectedPolymerase: "Q5",
    tmTolerance: 4,
    primerLenEnabled: true,
    fwdLenMin: 18,
    fwdLenMax: 39,
    revLenMin: 19,
    revLenMax: 27,
    overlapMode: "partial",
    strictOfftarget: false,
    randomSeed: null,
    designResults: [],
    failedMutations: [],
    successCount: 0,
    totalCount: 0,
    lastDesignRequest: null,
    logLines: [],
  } as never);
});

afterEach(() => {
  useAppStore.setState(pristine, true);
});

/** One designed mutation, one failure with the reason the user reported. */
function designResponse() {
  return {
    results: [
      {
        mutation: "F385Y",
        aa_position: 385,
        codon_pos: 1152,
        forward_seq: "ATGCATGCATGCATGCATGC",
        reverse_seq: "GCATGCATGCATGCATGCAT",
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
        wt_codon: "TTT",
        mt_codon: "TAT",
        overlap_seq: "ATGCATGCATGCATGCAT",
        warnings: [],
      },
    ],
    success_count: 1,
    total_count: 2,
    failed_mutations: [{ mutation: "K182N", rank: 1, reason: FAILURE_REASON }],
    rescue_stats: {
      pool_cascade: 0,
      auto_relax: 0,
      positions_attempted: 1,
      pool_variants_tried: 0,
    },
    rescued_mutations: [],
  };
}

async function runDesignThenBundle(): Promise<DiagnosticsBundle> {
  mocks.sendRequest.mockImplementation(async (method: string) => {
    if (method === "design_sdm_primers") return designResponse();
    throw new Error(`unexpected method ${method}`);
  });
  await useAppStore.getState().designPrimers();
  await generateDiagnosticsBundle();
  expect(mocks.writeTextFile).toHaveBeenCalledTimes(1);
  return JSON.parse(mocks.writeTextFile.mock.calls[0][1] as string) as DiagnosticsBundle;
}

describe("a real design run fills the run section", () => {
  it("records the parameters the run was launched with and the failure it produced", async () => {
    const bundle = await runDesignThenBundle();
    expect(bundle.run.status).toBe("recorded");
    if (bundle.run.status !== "recorded") return;
    // Not hand-seeded: designPrimers built this from the payload it sent.
    expect(bundle.run.request).toEqual({
      polymerase: "Q5",
      codon_strategy: "closest",
      organism: "ecoli",
      tm_fwd_target: 62,
      tm_rev_target: 58,
      tm_overlap_target: 42,
      tol_max: 4,
      gc_min: 40,
      gc_max: 60,
      fwd_len_min: 18,
      fwd_len_max: 39,
      rev_len_min: 19,
      rev_len_max: 27,
      overlap_mode: "partial",
      strict_offtarget: false,
      auto_relax: false,
      seed: null,
    });
    expect(bundle.run.summary).toEqual({ total: 2, success: 1, failed: 1 });
    expect(bundle.run.failures).toEqual([
      { mutation: "K182N", rank: 1, reason: FAILURE_REASON },
    ]);
  });

  it("carries neither the template path it was given nor the designed sequences", async () => {
    const serialized = JSON.stringify(await runDesignThenBundle());
    expect(serialized).not.toContain(SECRET_FASTA);
    expect(serialized).not.toContain("secret-campaign");
    expect(serialized).not.toContain("ATGCATGCATGCATGCATGC");
    // The mutation that succeeded is not the question being asked.
    expect(serialized).not.toContain("F385Y");
  });

  it("drops the run section again when a design input changes after the run", async () => {
    await runDesignThenBundle();
    useAppStore.getState().setGcRange(30, 70);
    mocks.writeTextFile.mockClear();
    await generateDiagnosticsBundle();
    const bundle = JSON.parse(
      mocks.writeTextFile.mock.calls[0][1] as string,
    ) as DiagnosticsBundle;
    expect(bundle.run).toEqual({ status: "no-run-data" });
  });

  it("keeps the failures but states the missing parameters when results come back from disk", async () => {
    await runDesignThenBundle();
    // What a restore leaves behind: results and failures without the request,
    // because no snapshot or workspace persists it.
    useAppStore.setState({ lastDesignRequest: null } as never);
    mocks.writeTextFile.mockClear();
    await generateDiagnosticsBundle();
    const bundle = JSON.parse(
      mocks.writeTextFile.mock.calls[0][1] as string,
    ) as DiagnosticsBundle;
    expect(bundle.run.status).toBe("recorded");
    if (bundle.run.status !== "recorded") return;
    expect(bundle.run.request).toBeNull();
    expect(bundle.run.rescue.requested).toBeNull();
    expect(bundle.run.failures).toEqual([
      { mutation: "K182N", rank: 1, reason: FAILURE_REASON },
    ]);
  });
});

/**
 * The default path. `fillOnFailure` is true in the store reset block, so a run
 * started from a fresh workspace goes through the post-design EVOLVEpro reload
 * and then cascadeFailedRetry. Both run after the set() that records the
 * request snapshot, and the cascade is the reason the snapshot exists: it sends
 * relaxed Tm/GC/length values that never reach the store.
 */
describe("the snapshot survives the fill-on-failure path", () => {
  const POOL = ["K182N", "Q163W", "F385Y"];

  function primer(mutation: string) {
    return { ...designResponse().results[0], mutation };
  }

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

  beforeEach(() => {
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      mutationText: POOL.join("\n"),
      evolveproCsvPath: "pool.csv",
      evolveproMode: "pipeline",
      evolveproSelectedVariants: [...POOL],
      evolveproRankedCandidates: POOL.map((variant, i) => ({ variant, y_pred: 1 - i * 0.1 })),
      poolVariants: [...POOL],
      fillOnFailure: true,
      maxPrimers: 3,
    } as never);
  });

  afterEach(() => {
    useAppStore.getState().cancelDiversityReload();
  });

  it("still reports the request, and counts the cascade rescue by stage", async () => {
    mocks.sendRequest.mockImplementation(
      async (method: string, params: Record<string, unknown>) => {
        if (method === "load_evolvepro_csv") return evolveproResponse(params);
        if (method === "design_sdm_primers") {
          return {
            results: [primer("F385Y")],
            success_count: 1,
            total_count: 3,
            failed_mutations: [
              { mutation: "K182N", rank: 1, reason: FAILURE_REASON },
              { mutation: "Q163W", rank: 2, reason: FAILURE_REASON },
            ],
            rescue_stats: {
              pool_cascade: 0,
              auto_relax: 0,
              positions_attempted: 2,
              pool_variants_tried: 0,
            },
            rescued_mutations: [],
          };
        }
        // Only K182N is recoverable; Q163W stays failed through every stage.
        if (method === "retry_failed_mutation") {
          return params.mutation === "K182N"
            ? { candidates: [primer("K182N")] }
            : { candidates: [] };
        }
        if (method === "commit_design_result") return {};
        throw new Error(`unexpected method ${method}`);
      },
    );

    await useAppStore.getState().designPrimers();
    await generateDiagnosticsBundle();
    const bundle = JSON.parse(
      mocks.writeTextFile.mock.calls[0][1] as string,
    ) as DiagnosticsBundle;

    expect(bundle.run.status).toBe("recorded");
    if (bundle.run.status !== "recorded") return;
    // The preserving EVOLVEpro reload and the cascade both ran after the
    // snapshot was stored, and neither cleared it.
    expect(bundle.run.request?.auto_relax).toBe(true);
    expect(bundle.run.request?.polymerase).toBe("Q5");
    expect(bundle.run.failures.map((f) => f.mutation)).toEqual(["Q163W"]);
    // rescuedMutations is written once from the sidecar reply and never again,
    // so a cascade rescue is only visible in rescuedMutationDetails. Counting
    // the first would report 0 here.
    expect(bundle.run.rescue.rescuedCount).toBe(1);
    expect(bundle.run.rescue.rescuedByStage).toEqual({ same_position: 1 });
    expect(JSON.stringify(bundle)).not.toContain("F385Y");
  });
});

/**
 * No snapshot and no workspace persists the design request, so both restore
 * paths null it rather than leave an earlier run's parameters standing next to
 * the failures they just loaded.
 */
describe("restoring results clears the request", () => {
  it("is nulled by the autosave hydration path", async () => {
    await runDesignThenBundle();
    expect(useAppStore.getState().lastDesignRequest).not.toBeNull();
    await applyKuroSnapshot({
      schema: 2,
      saved_at: new Date().toISOString(),
      kuma_version: "0.0.0-test",
      results: { designResults: [], successCount: 0, totalCount: 0, failedMutations: [] },
    } as unknown as AutosaveSnapshot);
    expect(useAppStore.getState().lastDesignRequest).toBeNull();
  });

  it("is nulled by a workspace restore", async () => {
    await runDesignThenBundle();
    expect(useAppStore.getState().lastDesignRequest).not.toBeNull();
    await useAppStore.getState().restoreWorkspace(
      {
        schema_version: "0.3",
        inputs: {},
        settings: {},
        results: { designResults: [], successCount: 0, totalCount: 0, failedMutations: [] },
        ui: {},
        cache: {},
      } as unknown as WorkspaceData,
      undefined,
    );
    expect(useAppStore.getState().lastDesignRequest).toBeNull();
  });
});
