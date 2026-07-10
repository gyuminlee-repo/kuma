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
