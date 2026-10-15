import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: mocks.send, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
vi.mock("@/lib/toast", () => ({ notifyJobError: vi.fn(), notifyJobDone: vi.fn(), notifyJobStarted: vi.fn() }));
vi.mock("@/lib/notify", () => ({ notifyJobComplete: vi.fn() }));
vi.mock("@/lib/keepAwake", () => ({ startKeepAwake: vi.fn(), stopKeepAwake: vi.fn() }));

import { useAppStore } from "../appStore";
import { strictSpatialFixture } from "@/test-utils/strictSpatialFixture";
import { strictSpatialContextKey } from "@/lib/strictSpatial";

function loadResponse(report = strictSpatialFixture()) {
  return { variants: report.selected_variants, y_preds: [2, 1], total_count: 4,
    selected_count: 2, pool_variants: ["A2G", "A3G", "A4V", "A5G"], strict_spatial: report,
    ranked_candidates: ["A2G", "A4V", "A5G"].map((variant, i) => ({ variant, aa_position: [2, 4, 5][i], y_pred: 2 - i })),
  };
}

beforeEach(() => {
  mocks.send.mockReset();
  useAppStore.setState({
    fastaPath: "/tmp/reference.fasta", selectedGene: "0",
    seqInfo: { header: "fixture", seq_length: 15, genes: [{ gene: "fixture", product: "test", cds_start: 0, cds_end: 15, aa_length: 5, translation: "MAAAA" }] },
    mutationInputMode: "evolvepro", evolveproMode: "pipeline", evolveproCsvPath: "/tmp/candidates.csv",
    structureAccession: "P12345", uniprotAccession: "P12345", structureLoaded: true,
    evolveproScoreOrder: "desc", evolveproVariantColumn: null, evolveproScoreColumn: null, evolveproSheetName: null,
    maxPrimers: 2, structuralDiversityEnabled: true, strictSpatialEnabled: true,
    strictSpatialSelection: null, strictSpatialError: null, evolveproSelectionManual: false,
    evolveproSelectedVariants: ["A2G", "A4V"], mutationText: "A2G\nA4V", fillOnFailure: true,
    requireNetworkConsent: vi.fn(async () => true), isDesigning: false,
  });
  useAppStore.setState({ strictSpatialSelection: { result: strictSpatialFixture(), contextKey: strictSpatialContextKey(useAppStore.getState()) } });
});
afterEach(() => useAppStore.getState().cancelDiversityReload());

describe("strict spatial design identity", () => {
  it.each([false, true])("aborts when strict mode changes during selection reload (initial=%s)", async (initial) => {
    useAppStore.setState({ strictSpatialEnabled: initial });
    let finish: ((value: ReturnType<typeof loadResponse>) => void) | undefined;
    mocks.send.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const pending = useAppStore.getState().designPrimers();
    await vi.waitFor(() => expect(finish).toBeDefined());
    useAppStore.getState().setStrictSpatialEnabled(!initial);
    finish?.(loadResponse());
    await pending;
    expect(mocks.send.mock.calls.some(([method]) => method === "design_sdm_primers")).toBe(false);
    expect(useAppStore.getState().statusMessage).toContain("Review the updated selection");
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
  });

  it("designs the reviewed IDs at exactly N with all replacement disabled", async () => {
    mocks.send.mockImplementation(async (method, params) => {
      if (method === "load_evolvepro_csv") return loadResponse();
      if (method === "design_sdm_primers") return { results: [], success_count: 0, total_count: 2,
        failed_mutations: params.mutations_csv_or_text.split("\n").map((mutation: string, rank: number) => ({ mutation, rank, reason: "test failure" })) };
      throw Error(`Unexpected ${method}`);
    });
    await useAppStore.getState().designPrimers();
    const loads = mocks.send.mock.calls.filter(([method]) => method === "load_evolvepro_csv");
    expect(loads).toHaveLength(1);
    expect(loads[0][1]).toMatchObject({ top_n: 2, strict_spatial: true, structural_diversity: true });
    const design = mocks.send.mock.calls.find(([method]) => method === "design_sdm_primers");
    expect(design?.[1].mutations_csv_or_text.split("\n").sort()).toEqual(["A2G", "A4V"]);
    expect(design?.[1].rescue_pool).toBeUndefined();
    expect(design?.[1].auto_relax).toBe(false);
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual(["A2G", "A4V"]);
    expect(useAppStore.getState().fillOnFailure).toBe(true); // preference survives the strict run
  });
  it.each(["source_sha256", "reference_sha256", "candidate_sha256"] as const)("requires another review when %s changes even if IDs match", async (field) => {
    mocks.send.mockResolvedValue(loadResponse(strictSpatialFixture({ [field]: "d".repeat(64) })));
    await useAppStore.getState().designPrimers();
    expect(mocks.send.mock.calls.some(([method]) => method === "design_sdm_primers")).toBe(false);
    expect(useAppStore.getState().statusMessage).toContain("Review the updated selection");
  });
  it("blocks design when the candidate controls no longer match the preview", async () => {
    useAppStore.setState({ evolveproScoreOrder: "asc" });
    await useAppStore.getState().designPrimers();
    expect(mocks.send).not.toHaveBeenCalled();
    expect(useAppStore.getState().statusMessage).toContain("Select and review");
  });
  it("rejects a legacy sidecar response without quietly selecting in 1D", async () => {
    mocks.send.mockResolvedValue({ ...loadResponse(), strict_spatial: undefined });
    await expect(useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv")).rejects.toThrow("verified strict spatial selection");
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual([]);
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
    expect(useAppStore.getState().strictSpatialError).toContain("Update the sidecar");
  });
  it("reports capacity failure and retains no stale selection", async () => {
    mocks.send.mockRejectedValue(Error("Strict spatial count 2 exceeds 1 eligible unique sites"));
    await expect(useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv")).rejects.toThrow("eligible unique sites");
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual([]);
  });
  it("rejects local file sources before any remote request", async () => {
    useAppStore.setState({ structureAccession: "file:/tmp/custom.pdb" });
    await expect(useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv")).rejects.toThrow("Local structure files");
    expect(mocks.send).not.toHaveBeenCalled();
    expect(useAppStore.getState().requireNetworkConsent).not.toHaveBeenCalled();
  });
  it("does not let manual selection create an uncertified strict set", () => {
    useAppStore.getState().setEvolveproVariantSelected("A5G", true);
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual(["A2G", "A4V"]);
  });
  it("does not accept a response belonging to a previous reference", async () => {
    let finish: ((value: ReturnType<typeof loadResponse>) => void) | undefined;
    mocks.send.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const pending = useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv");
    await vi.waitFor(() => expect(finish).toBeDefined());
    useAppStore.setState({ structureAccession: "OTHER" });
    finish?.(loadResponse());
    await pending;
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
  });
});
