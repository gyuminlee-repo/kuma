import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: mocks.send, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "../appStore";
import { currentStrictSpatialResult, strictSpatialContextKey } from "@/lib/strictSpatial";
import { importedSpatialFixture, predictionBundleInventory } from "@/test-utils/predictionBundleFixture";

const initial = useAppStore.getState();
beforeEach(() => {
  mocks.send.mockReset();
  useAppStore.setState(initial, true);
  useAppStore.setState({ strictSpatialEnabled: true, structuralDiversityEnabled: true,
    evolveproMode: "pipeline", mutationInputMode: "evolvepro", maxPrimers: 2,
    requireNetworkConsent: vi.fn(async () => false),
    seqInfo: { header: "reference", seq_length: 15, genes: [{ gene: "reference", product: "test",
      cds_start: 0, cds_end: 15, aa_length: 5, translation: "MAAAA" }] }, selectedGene: "0" });
});
afterEach(() => useAppStore.getState().cancelDiversityReload());

function configure() {
  const inventory = predictionBundleInventory();
  useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundlePath: "/tmp/prediction.zip",
    predictionBundleInventory: inventory, predictionBundleModelId: inventory.models[0].model_id, predictionBundleChainId: "A" });
}
function response(report = importedSpatialFixture()) {
  return { strict_spatial: report, variants: report.selected_variants, y_preds: [2, 1],
    selected_count: 2, total_count: 3 };
}

describe("local prediction import state", () => {
  it("defaults to the verified producer top model but requires a chain after every inspected ZIP", async () => {
    mocks.send.mockResolvedValue(predictionBundleInventory());
    await useAppStore.getState().inspectPredictionBundle("/tmp/prediction.zip");
    expect(mocks.send).toHaveBeenCalledWith("inspect_prediction_bundle", { filepath: "/tmp/prediction.zip" });
    expect(useAppStore.getState().predictionBundleModelId).toBe("job_model_0.cif");
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
    useAppStore.getState().setPredictionBundleModelId("job_model_1.cif");
    useAppStore.getState().setPredictionBundleChainId("B");
    await useAppStore.getState().inspectPredictionBundle("/tmp/prediction.zip");
    expect(useAppStore.getState().predictionBundleModelId).toBe("job_model_0.cif");
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
    expect(useAppStore.getState().requireNetworkConsent).not.toHaveBeenCalled();
  });

  it("uses the backend recommendation rather than the first inventory entry", async () => {
    const inventory = predictionBundleInventory();
    inventory.models.reverse();
    mocks.send.mockResolvedValue(inventory);
    await useAppStore.getState().inspectPredictionBundle("/tmp/prediction.zip");
    expect(useAppStore.getState().predictionBundleModelId).toBe("job_model_0.cif");
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
  });

  it.each(["missing_top_rank", "ambiguous_ranking"] as const)("never substitutes a model for %s", async (reason) => {
    mocks.send.mockResolvedValue({ ...predictionBundleInventory(), recommended_model_id: null,
      recommendation_reason: reason });
    await useAppStore.getState().inspectPredictionBundle("/tmp/prediction.zip");
    expect(useAppStore.getState().predictionBundleModelId).toBeNull();
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
  });

  it("does not select a fallback after inspection rejects an incomplete top model", async () => {
    configure();
    mocks.send.mockRejectedValue(Error("Missing paired prediction member"));
    await useAppStore.getState().inspectPredictionBundle("/tmp/broken.zip");
    expect(useAppStore.getState().predictionBundleInventory).toBeNull();
    expect(useAppStore.getState().predictionBundleModelId).toBeNull();
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
  });

  it("does not auto-select even a single chain before reference correspondence is verified", async () => {
    const inventory = predictionBundleInventory();
    inventory.models[0].chains = [inventory.models[0].chains[0]];
    mocks.send.mockResolvedValue(inventory);
    await useAppStore.getState().inspectPredictionBundle("/tmp/prediction.zip");
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
  });

  it.each(["same-file", "different-file", "source-switch", "reset"])("ignores stale inventory responses after %s", async (mode) => {
    let finish: ((value: ReturnType<typeof predictionBundleInventory>) => void) | undefined;
    mocks.send.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const pending = useAppStore.getState().inspectPredictionBundle("/tmp/first.zip");
    if (mode === "reset") useAppStore.getState().resetAll();
    else if (mode === "source-switch") useAppStore.getState().setStrictStructureSource("accession");
    else {
      mocks.send.mockResolvedValue({ ...predictionBundleInventory(), source_name: "latest.zip", bundle_sha256: "e".repeat(64) });
      await useAppStore.getState().inspectPredictionBundle(mode === "same-file" ? "/tmp/first.zip" : "/tmp/latest.zip");
    }
    finish?.(predictionBundleInventory());
    await pending;
    expect(useAppStore.getState().predictionBundleInventory?.source_name).toBe(mode === "source-switch" || mode === "reset" ? undefined : "latest.zip");
    expect(useAppStore.getState().predictionBundleLoading).toBe(false);
  });

  it("keeps the selected model but clears chain/certificate when switching models", () => {
    configure();
    const report = importedSpatialFixture();
    useAppStore.setState({ evolveproSelectedVariants: report.selected_variants,
      strictSpatialSelection: { result: report, contextKey: strictSpatialContextKey(useAppStore.getState()) } });
    expect(currentStrictSpatialResult(useAppStore.getState())).toBe(report);
    useAppStore.getState().setPredictionBundleModelId("job_model_1.cif");
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
    expect(currentStrictSpatialResult(useAppStore.getState())).toBeNull();
    useAppStore.getState().setPredictionBundleChainId("unknown");
    expect(useAppStore.getState().predictionBundleChainId).toBeNull();
  });

  it("preserves the accession configuration when switching sources", () => {
    configure();
    useAppStore.setState({ structureAccession: "P12345", uniprotAccession: "P12345" });
    useAppStore.getState().setStrictStructureSource("accession");
    expect(useAppStore.getState().structureAccession).toBe("P12345");
    expect(useAppStore.getState().predictionBundlePath).toBe("/tmp/prediction.zip");
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
  });

  it("sends the exact local identity and inspected hash without network consent", async () => {
    configure();
    mocks.send.mockResolvedValue(response());
    await useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv");
    expect(mocks.send).toHaveBeenCalledWith("load_evolvepro_csv", expect.objectContaining({
      prediction_bundle_path: "/tmp/prediction.zip", prediction_model_id: "job_model_0.cif",
      prediction_chain_id: "A", prediction_bundle_sha256: "d".repeat(64), ref_seq: "MAAAA", strict_spatial: true,
    }));
    expect(mocks.send.mock.calls[0][1]).not.toHaveProperty("structure_accession");
    expect(useAppStore.getState().requireNetworkConsent).not.toHaveBeenCalled();
    expect(currentStrictSpatialResult(useAppStore.getState())?.prediction_bundle?.model_id).toBe("job_model_0.cif");
  });

  it.each(["bundle_sha256", "model_id", "chain_id", "structure_sha256"] as const)("rejects stale/mismatched %s", async (field) => {
    configure();
    mocks.send.mockResolvedValue(response(importedSpatialFixture({ [field]: "wrong" })));
    await expect(useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv")).rejects.toThrow("verified strict spatial selection");
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
  });

  it("blocks incomplete explicit selection before any RPC", async () => {
    configure();
    useAppStore.setState({ predictionBundleChainId: null });
    await expect(useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv")).rejects.toThrow("Choose a saved ZIP");
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it.each([false, true])("does not restore an old selection/error after source changes away and back (error=%s)", async (reject) => {
    configure();
    let finish: (() => void) | undefined;
    mocks.send.mockImplementation(() => new Promise((resolve, failure) => {
      finish = () => reject ? failure(Error("old error")) : resolve(response());
    }));
    const pending = useAppStore.getState().loadEvolveproCsv("/tmp/candidates.csv");
    useAppStore.getState().setStrictStructureSource("accession");
    useAppStore.getState().setStrictStructureSource("prediction_bundle");
    finish?.();
    await pending;
    expect(useAppStore.getState().strictSpatialSelection).toBeNull();
    expect(useAppStore.getState().strictSpatialError).toBeNull();
  });
});
