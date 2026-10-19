import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { sendRequest } from "../../lib/ipc-kuro";
import { createDiversitySlice } from "./diversitySlice";

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
}));

vi.mock("i18next", () => ({
  default: { t: (key: string) => key },
}));

const mockedSendRequest = vi.mocked(sendRequest);

function makeStore(consent = true) {
  const state: Record<string, unknown> = {
    offlineMode: false,
    statusMessage: "",
    requireNetworkConsent: vi.fn().mockResolvedValue(consent),
    // The real store carries this alongside requireNetworkConsent; a refusal is
    // reported differently depending on whether the service itself was switched
    // off in Settings.
    isNetworkServiceEnabled: () => true,
  };
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u);
  };
  const get = () => state as unknown as AppState;
  const slice = createDiversitySlice(
    set as Parameters<typeof createDiversitySlice>[0],
    get as Parameters<typeof createDiversitySlice>[1],
    {} as Parameters<typeof createDiversitySlice>[2],
  );
  Object.assign(state, slice);
  return { state, slice };
}

const OK_RESULT = {
  success: true,
  source: "esmfold" as const,
  pdb_text: "ATOM ...",
  plddt_mean: 88.5,
  residue_count: 120,
  coordinate_frame: "reference" as const,
  seq_hash: "abc",
  cache_hit: false,
};

describe("predictStructureEsmfold", () => {
  beforeEach(() => mockedSendRequest.mockReset());

  it("submits the sequence and returns the predicted structure", async () => {
    mockedSendRequest.mockResolvedValueOnce(OK_RESULT);
    const { slice } = makeStore();

    const result = await slice.predictStructureEsmfold("MKTAYIAKQR");

    expect(mockedSendRequest).toHaveBeenCalledWith(
      "predict_structure_esmfold",
      { sequence: "MKTAYIAKQR" },
      180_000,
    );
    expect(result?.success).toBe(true);
    expect(result?.coordinate_frame).toBe("reference");
  });

  it("does not call the service without consent", async () => {
    const { slice } = makeStore(false);
    const result = await slice.predictStructureEsmfold("MKTAYIAKQR");
    expect(mockedSendRequest).not.toHaveBeenCalled();
    expect(result).toBeNull();
  });

  it("caches per sequence so a repeat call does not re-submit", async () => {
    mockedSendRequest.mockResolvedValueOnce(OK_RESULT);
    const { slice } = makeStore();
    await slice.predictStructureEsmfold("MKTAYIAKQR");
    await slice.predictStructureEsmfold("MKTAYIAKQR");
    expect(mockedSendRequest).toHaveBeenCalledTimes(1);
  });

  it("surfaces a backend error result and drops it from the cache", async () => {
    mockedSendRequest
      .mockResolvedValueOnce({
        success: false,
        source: "error",
        pdb_text: null,
        plddt_mean: 0,
        residue_count: 0,
        coordinate_frame: "reference",
        seq_hash: "",
        cache_hit: false,
        error_msg: "too long",
      })
      .mockResolvedValueOnce(OK_RESULT);
    const { slice } = makeStore();

    const first = await slice.predictStructureEsmfold("MKTAYIAKQR");
    expect(first?.source).toBe("error");

    // A failed prediction must not be cached: the retry re-submits.
    const second = await slice.predictStructureEsmfold("MKTAYIAKQR");
    expect(second?.success).toBe(true);
    expect(mockedSendRequest).toHaveBeenCalledTimes(2);
  });
});

describe("fetchDomains with an ESMFold structure", () => {
  beforeEach(() => mockedSendRequest.mockReset());

  it("keeps the ESMFold key instead of reverting to the AlphaFold accession", async () => {
    mockedSendRequest.mockResolvedValueOnce({ domains: [], source: "interpro" } as never);
    const { state, slice } = makeStore();
    state.structureAccession = "ESMFOLD:ABC";
    state.structureLoaded = true;
    state.fetchStructure = vi.fn();

    await slice.fetchDomains("P12345");

    expect(state.structureAccession).toBe("ESMFOLD:ABC");
    expect(state.structureLoaded).toBe(true);
    expect(state.fetchStructure).not.toHaveBeenCalled();
  });
});

describe("adoptReferenceEsmfold", () => {
  beforeEach(() => mockedSendRequest.mockReset());

  it("makes the prediction the structure selection reads", async () => {
    mockedSendRequest.mockResolvedValueOnce({ ...OK_RESULT, structure_key: "ESMFOLD:ABC" });
    const { state, slice } = makeStore();

    const outcome = await slice.adoptReferenceEsmfold("MKTAYIAKQR");

    expect(outcome).toBe("used");
    expect(state.structureAccession).toBe("ESMFOLD:ABC");
    expect(state.structureLoaded).toBe(true);
  });

  it("reports a refusal without calling the service or touching the structure", async () => {
    const { state, slice } = makeStore(false);

    const outcome = await slice.adoptReferenceEsmfold("MKTAYIAKQR");

    expect(outcome).toBe("refused");
    expect(mockedSendRequest).not.toHaveBeenCalled();
    expect(state.structureAccession).toBe("");
  });

  it("asks for network consent once", async () => {
    mockedSendRequest.mockResolvedValueOnce({ ...OK_RESULT, structure_key: "ESMFOLD:ABC" });
    const { state, slice } = makeStore();

    await slice.adoptReferenceEsmfold("MKTAYIAKQR");

    expect(state.requireNetworkConsent).toHaveBeenCalledTimes(1);
  });

  it("drops a prediction that finishes after the accession changed", async () => {
    let finish!: (value: unknown) => void;
    mockedSendRequest.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }) as never);
    const { state, slice } = makeStore();
    state.uniprotAccession = "P12345";

    const pending = slice.adoptReferenceEsmfold("MKTAYIAKQR");
    await vi.waitFor(() => expect(mockedSendRequest).toHaveBeenCalledTimes(1));
    state.uniprotAccession = "Q99999";
    finish({ ...OK_RESULT, structure_key: "ESMFOLD:ABC" });

    expect(await pending).toBe("stale");
    expect(state.structureAccession).toBe("");
    expect(state.structureLoaded).toBe(false);
  });

  it("drops a prediction that finishes after the reference sequence changed", async () => {
    let finish!: (value: unknown) => void;
    mockedSendRequest.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }) as never);
    const { state, slice } = makeStore();
    state.seqInfo = { genes: [{ cds_start: 1, translation: "MKTAYIAKQR" }] };

    const pending = slice.adoptReferenceEsmfold("MKTAYIAKQR");
    await vi.waitFor(() => expect(mockedSendRequest).toHaveBeenCalledTimes(1));
    state.seqInfo = { genes: [{ cds_start: 1, translation: "MKTAYIAKQRLL" }] };
    finish({ ...OK_RESULT, structure_key: "ESMFOLD:ABC" });

    expect(await pending).toBe("stale");
    expect(state.structureAccession).toBe("");
  });

  it("drops a prediction that finishes after a newer structure request took over", async () => {
    let finishPredict!: (value: unknown) => void;
    mockedSendRequest.mockImplementation(((method: string) => method === "predict_structure_esmfold"
      ? new Promise((resolve) => { finishPredict = resolve; })
      : Promise.resolve({ success: true, residues: 120 })) as never);
    const { state, slice } = makeStore();
    state.uniprotAccession = "P12345";

    const pending = slice.adoptReferenceEsmfold("MKTAYIAKQR");
    await vi.waitFor(() => expect(mockedSendRequest).toHaveBeenCalledTimes(1));
    await slice.fetchStructure("P12345");
    finishPredict({ ...OK_RESULT, structure_key: "ESMFOLD:ABC" });

    expect(await pending).toBe("stale");
    expect(state.structureAccession).toBe("P12345");
  });

  it("leaves an in-flight structure fetch alone when the prediction fails", async () => {
    let finishFetch!: (value: unknown) => void;
    mockedSendRequest.mockImplementation(((method: string) => method === "fetch_structure"
      ? new Promise((resolve) => { finishFetch = resolve; })
      : Promise.resolve({ ...OK_RESULT, success: false, source: "error", pdb_text: null })) as never);
    const { state, slice } = makeStore();
    state.uniprotAccession = "P12345";

    const fetching = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(mockedSendRequest).toHaveBeenCalledTimes(1));
    expect(await slice.adoptReferenceEsmfold("MKTAYIAKQR")).toBe("failed");
    finishFetch({ success: true, residues: 120 });
    await fetching;

    expect(state.structureLoading).toBe(false);
    expect(state.structureLoaded).toBe(true);
    expect(state.structureAccession).toBe("P12345");
  });

  it.each(["fetch_structure", "load_structure_file"] as const)(
    "does not let a cached prediction replace an in-flight %s request",
    async (request) => {
    const completion: { resolve?: (value: { success: boolean; residues: number; accession: string }) => void } = {};
    const started = new Promise<void>((resolveStarted) => {
      mockedSendRequest.mockImplementation(((method: string) => method === request
        ? new Promise((resolve) => {
            completion.resolve = resolve;
            resolveStarted();
          })
        : Promise.resolve({ ...OK_RESULT, structure_key: "ESMFOLD:ABC" })) as never);
    });
    const { state, slice } = makeStore();
    state.uniprotAccession = "P12345";
    await slice.predictStructureEsmfold("MKTAYIAKQR");
    state.structure3dState = "frame_mismatch";
    state.structureCoverage = { covered: 8, reference_length: 10 };

    const fetching = request === "fetch_structure"
      ? slice.fetchStructure("P12345")
      : slice.loadStructureFile("/tmp/synthetic.pdb");
    await started;
    expect(state.structure3dState).toBe("off");
    expect(state.structureCoverage).toBeNull();
    expect(await slice.adoptReferenceEsmfold("MKTAYIAKQR")).toBe("stale");
    expect(state.structureLoading).toBe(true);
    const accession = request === "fetch_structure" ? "P12345" : "file:synthetic";
    completion.resolve?.({ success: true, residues: 120, accession });
    await fetching;

    expect(state.structureLoading).toBe(false);
    expect(state.structureAccession).toBe(accession);
  });

  it("reports a prediction without a structure key as failed", async () => {
    mockedSendRequest.mockResolvedValueOnce({ ...OK_RESULT, success: false, source: "error", pdb_text: null });
    const { state, slice } = makeStore();

    expect(await slice.adoptReferenceEsmfold("MKTAYIAKQR")).toBe("failed");
    expect(state.structureAccession).toBe("");
  });
});
