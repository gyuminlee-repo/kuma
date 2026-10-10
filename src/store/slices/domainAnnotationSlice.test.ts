import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: mocks.send, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "../appStore";
import { colabFoldDomainInventory, domainJobFixture, domainReferenceFixture, domainResultFixture, domainRuntimeFixture } from "@/test-utils/domainAnnotationFixture";
import { currentDomainAnnotation, domainAnnotationContextKey } from "@/lib/domainAnnotation";

const initial = useAppStore.getState();
const state = () => useAppStore.getState();
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((r) => { resolve = r; }); return { promise, resolve }; }
function setup() {
  useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundlePath: "/tmp/saved.zip",
    predictionBundleInventory: colabFoldDomainInventory(), predictionBundleModelId: "job_model_0.cif", predictionBundleChainId: "A",
    seqInfo: domainReferenceFixture, selectedGene: "1", domainRuntimeStatus: domainRuntimeFixture(),
    evolveproSelectedVariants: ["A2V", "A2G", "A4G"], mutationText: "A2V\nA2G\nA4G", maxPrimers: 3 });
}
beforeEach(() => { vi.stubGlobal("crypto", webcrypto); vi.useFakeTimers(); mocks.send.mockReset(); useAppStore.setState(initial, true); setup(); });
afterEach(() => { vi.unstubAllGlobals(); useAppStore.setState(initial, true); vi.clearAllTimers(); vi.useRealTimers(); });

describe("optional annotation session", () => {
  it("never bypasses an empty approved catalog", async () => {
    useAppStore.setState({ domainRuntimeStatus: domainRuntimeFixture({ state: "licensing_blocked", version: null, install_available: false, available_version: null }) });
    await state().startDomainAnnotation(); await state().installDomainRuntime("/tmp/unreviewed.zip");
    expect(mocks.send).not.toHaveBeenCalled();
  });
  it("polls a managed job, imports its completed result, and leaves scientific selection unchanged", async () => {
    const before = { variants: state().evolveproSelectedVariants, text: state().mutationText, n: state().maxPrimers,
      strict: state().strictSpatialSelection, scores: state().yPredMap, position: state().positionDiversityEnabled };
    mocks.send.mockResolvedValueOnce(domainJobFixture()).mockResolvedValueOnce(domainJobFixture("running"))
      .mockResolvedValueOnce(domainJobFixture("succeeded")).mockResolvedValueOnce(domainResultFixture("managed"));
    await state().startDomainAnnotation();
    expect(mocks.send).toHaveBeenNthCalledWith(1, "start_domain_annotation", expect.objectContaining({ prediction_bundle_path: "/tmp/saved.zip", ref_seq: "MAAAA" }), 120_000);
    expect(state().domainAnnotationResult).toBeNull();
    await vi.advanceTimersByTimeAsync(1500); expect(state().domainAnnotationJob?.state).toBe("running");
    await state().pollDomainAnnotation();
    expect(currentDomainAnnotation(state())).toEqual(domainResultFixture("managed"));
    expect(state().domainAnnotationPending).toBeNull();
    expect({ variants: state().evolveproSelectedVariants, text: state().mutationText, n: state().maxPrimers,
      strict: state().strictSpatialSelection, scores: state().yPredMap, position: state().positionDiversityEnabled }).toEqual(before);
  });
  it("imports a job that completed before the start reply arrived", async () => {
    mocks.send.mockResolvedValueOnce(domainJobFixture("succeeded")).mockResolvedValueOnce(domainResultFixture("managed"));
    await state().startDomainAnnotation();
    expect(currentDomainAnnotation(state())).toEqual(domainResultFixture("managed"));
  });
  it("cancel waits for confirmed termination and never imports the cancelled run", async () => {
    mocks.send.mockResolvedValueOnce(domainJobFixture("running")).mockResolvedValueOnce(domainJobFixture("cancelling"))
      .mockResolvedValueOnce(domainJobFixture("cancelled"));
    await state().startDomainAnnotation(); await state().cancelDomainAnnotation();
    expect(state().domainAnnotationJob?.state).toBe("cancelling");
    expect(state().domainAnnotationPending).toBe("cancelling");
    await vi.advanceTimersByTimeAsync(1500);
    expect(state().domainAnnotationJob?.state).toBe("cancelled");
    expect(state().domainAnnotationPending).toBeNull();
    expect(mocks.send.mock.calls.map((call) => call[0])).not.toContain("import_domain_annotation_result");
  });
  it("cancels a late start after reset, without allowing a replacement before its handle arrives", async () => {
    const start = deferred<ReturnType<typeof domainJobFixture>>();
    mocks.send.mockImplementation((method, params) => {
      if (method === "start_domain_annotation") return start.promise;
      if (method === "cancel_domain_annotation_attempt") return Promise.resolve({ attempt_id: params.attempt_id, state: "pending", message: "Preparing", job: null });
      return Promise.resolve(domainJobFixture("cancelled"));
    });
    const pending = state().startDomainAnnotation();
    state().resetDomainAnnotation();
    expect(state().domainAnnotationPending).toBe("cancelling");
    await state().startDomainAnnotation(); expect(mocks.send).toHaveBeenCalledTimes(2);
    start.resolve(domainJobFixture("running")); await pending;
    expect(mocks.send).toHaveBeenLastCalledWith("cancel_domain_annotation", { job_id: "1".repeat(32) });
    expect(state().domainAnnotationJob?.state).toBe("cancelled");
    expect(state().domainAnnotationResult).toBeNull();
  });
  it.each(["source", "model", "chain", "reference", "reimport", "reset"])("invalidates an imported result after %s changes, including an ABA return", async (change) => {
    const result = deferred<ReturnType<typeof domainResultFixture>>(); mocks.send.mockReturnValueOnce(result.promise);
    const pending = state().importDomainAnnotationFile("/tmp/result.json");
    if (change === "source") state().setStrictStructureSource("accession");
    if (change === "model") state().setPredictionBundleModelId("job_model_1.cif");
    if (change === "chain") state().setPredictionBundleChainId("B");
    if (change === "reference") useAppStore.setState({ selectedGene: "other" });
    if (change === "reimport") useAppStore.setState({ predictionBundleRevision: state().predictionBundleRevision + 1 });
    if (change === "reset") state().resetAll();
    setup(); // Same file/model/chain/ref again must still not revive an old request.
    result.resolve(domainResultFixture()); await pending;
    expect(currentDomainAnnotation(state())).toBeNull();
    expect(state().domainAnnotationPending).toBeNull();
  });
  it("cancels an exact lost-start attempt instead of assuming the process stopped", async () => {
    mocks.send.mockImplementation((method, params) => {
      if (method === "start_domain_annotation") return Promise.reject(new Error("Start response lost"));
      return Promise.resolve({ attempt_id: params.attempt_id, state: "cancelled", message: "No active process", job: null });
    });
    await state().startDomainAnnotation();
    const attemptId = mocks.send.mock.calls[0][1].attempt_id;
    expect(attemptId).toMatch(/^[a-f0-9]{32}$/);
    expect(mocks.send).toHaveBeenLastCalledWith("cancel_domain_annotation_attempt", { attempt_id: attemptId });
    expect(state().domainAnnotationAttempt?.state).toBe("cancelled");
    expect(state().domainAnnotationPending).toBeNull();
    expect(state().domainAnnotationResult).toBeNull();
  });
  it("keeps an ambiguous lost-start cancellation pending until exact recovery confirms termination", async () => {
    let attemptId = "";
    mocks.send.mockImplementation((method, params) => {
      if (method === "start_domain_annotation") { attemptId = params.attempt_id; return Promise.reject(new Error("Start response lost")); }
      return Promise.reject(new Error("Recovery temporarily unavailable"));
    });
    await state().startDomainAnnotation();
    expect(state().domainAnnotationPending).toBe("cancelling");
    mocks.send.mockResolvedValueOnce({ attempt_id: attemptId, state: "job", message: "Stopping", job: domainJobFixture("cancelling") })
      .mockResolvedValueOnce(domainJobFixture("cancelled"));
    await vi.advanceTimersByTimeAsync(1500);
    expect(state().domainAnnotationPending).toBe("cancelling");
    expect(state().domainAnnotationJob?.state).toBe("cancelling");
    await vi.advanceTimersByTimeAsync(1500);
    expect(state().domainAnnotationJob?.state).toBe("cancelled");
    expect(state().domainAnnotationPending).toBeNull();
  });
  it("ignores a late start response after exact pre-dispatch cancellation was confirmed", async () => {
    const start = deferred<ReturnType<typeof domainJobFixture>>();
    mocks.send.mockImplementation((method, params) => method === "start_domain_annotation" ? start.promise
      : Promise.resolve({ attempt_id: params.attempt_id, state: "cancelled", message: "Cancelled before dispatch", job: null }));
    const pending = state().startDomainAnnotation();
    await state().cancelDomainAnnotation();
    expect(state().domainAnnotationAttempt?.state).toBe("cancelled");
    start.resolve(domainJobFixture("queued")); await pending;
    expect(state().domainAnnotationJob).toBeNull();
    expect(state().domainAnnotationPending).toBeNull();
  });
  it("ignores an older import after an explicit clear and a newer import", async () => {
    const first = deferred<ReturnType<typeof domainResultFixture>>();
    mocks.send.mockReturnValueOnce(first.promise).mockResolvedValueOnce(domainResultFixture());
    const pending = state().importDomainAnnotationFile("/tmp/old.json"); state().resetDomainAnnotation();
    await state().importDomainAnnotationFile("/tmp/new.json");
    const newest = state().domainAnnotationResult;
    first.resolve({ ...domainResultFixture(), confidence: 0.1 }); await pending;
    expect(state().domainAnnotationResult).toBe(newest);
  });
  it("clears existing annotations immediately when model/chain/reference changes while the panel is hidden", async () => {
    useAppStore.setState({ domainAnnotationResult: domainResultFixture(), domainAnnotationContext: domainAnnotationContextKey(state()) });
    state().setPredictionBundleChainId("B");
    expect(state().domainAnnotationResult).toBeNull();
  });
  it("refuses AF3 run and import without making an RPC", async () => {
    useAppStore.setState({ predictionBundleInventory: { ...colabFoldDomainInventory(), format: "af3_server" } });
    await state().startDomainAnnotation(); await state().importDomainAnnotationFile("/tmp/result.json");
    expect(mocks.send).not.toHaveBeenCalled();
  });
  it("does not let a late running poll resurrect a cancelled job", async () => {
    const poll = deferred<ReturnType<typeof domainJobFixture>>();
    mocks.send.mockResolvedValueOnce(domainJobFixture("running")).mockReturnValueOnce(poll.promise)
      .mockResolvedValueOnce(domainJobFixture("cancelled"));
    await state().startDomainAnnotation(); const pendingPoll = state().pollDomainAnnotation();
    await state().cancelDomainAnnotation(); poll.resolve(domainJobFixture("running")); await pendingPoll;
    expect(state().domainAnnotationJob?.state).toBe("cancelled");
  });
  it("keeps polling after a transient poll failure until termination is known", async () => {
    mocks.send.mockResolvedValueOnce(domainJobFixture("running")).mockRejectedValueOnce(new Error("temporarily unreachable"))
      .mockResolvedValueOnce(domainJobFixture("failed"));
    await state().startDomainAnnotation(); await vi.advanceTimersByTimeAsync(1500);
    expect(state().domainAnnotationJob?.state).toBe("running");
    expect(state().domainAnnotationError).toContain("temporarily unreachable");
    await vi.advanceTimersByTimeAsync(1500); expect(state().domainAnnotationJob?.state).toBe("failed");
  });
  it("rejects a same-length wrong-reference hash from an imported result", async () => {
    mocks.send.mockResolvedValueOnce({ ...domainResultFixture(), binding: { ...domainResultFixture().binding, reference_sha256: "f".repeat(64) } });
    await state().importDomainAnnotationFile("/tmp/wrong-reference.json");
    expect(state().domainAnnotationResult).toBeNull();
    expect(state().domainAnnotationError).toMatch(/identity/);
  });
  it("cancels a start whose returned reference hash mismatches the selected sequence", async () => {
    const wrong = { ...domainJobFixture("running"), binding: { ...domainJobFixture().binding, reference_sha256: "f".repeat(64) } };
    mocks.send.mockResolvedValueOnce(wrong).mockResolvedValueOnce({ ...wrong, state: "cancelled" });
    await state().startDomainAnnotation();
    expect(mocks.send).toHaveBeenLastCalledWith("cancel_domain_annotation", { job_id: wrong.job_id });
    expect(state().domainAnnotationResult).toBeNull();
  });
  it("rechecks context after the asynchronous reference-hash validation", async () => {
    const digest = deferred<ArrayBuffer>();
    const hash = vi.spyOn(crypto.subtle, "digest").mockReturnValueOnce(digest.promise);
    mocks.send.mockResolvedValueOnce(domainResultFixture());
    const pending = state().importDomainAnnotationFile("/tmp/old-reference.json");
    await Promise.resolve(); expect(hash).toHaveBeenCalledOnce();
    state().setPredictionBundleChainId("B");
    digest.resolve(Uint8Array.from(domainResultFixture().binding.reference_sha256.match(/../g) ?? [], (hex) => parseInt(hex, 16)).buffer);
    await pending; hash.mockRestore();
    expect(state().domainAnnotationResult).toBeNull();
  });
  it("rejects mismatched import identity and leaves selected variants intact", async () => {
    mocks.send.mockResolvedValueOnce({ ...domainResultFixture(), binding: { ...domainResultFixture().binding, chain_id: "B" } });
    await state().importDomainAnnotationFile("/tmp/wrong.json");
    expect(state().domainAnnotationResult).toBeNull(); expect(state().domainAnnotationError).toMatch(/identity/);
    expect(state().evolveproSelectedVariants).toEqual(["A2V", "A2G", "A4G"]);
  });
});
