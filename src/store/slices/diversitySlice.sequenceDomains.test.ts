import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { sendRequest } from "../../lib/ipc-kuro";
import { createDiversitySlice } from "./diversitySlice";

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
}));

vi.mock("i18next", () => ({
  default: {
    t: (key: string) => key,
  },
}));

const mockedSendRequest = vi.mocked(sendRequest);

function makeStore(consent = true) {
  const state: Record<string, unknown> = {
    seqInfo: {
      header: "reference",
      seq_length: 60,
      genes: [{
        gene: "target",
        product: "target protein",
        cds_start: 1,
        cds_end: 180,
        aa_length: 60,
        translation: "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQ",
      }],
    },
    selectedGene: "1",
    offlineMode: false,
    statusMessage: "",
    requireNetworkConsent: vi.fn().mockResolvedValue(consent),
    loadEvolveproCsv: vi.fn().mockResolvedValue(undefined),
    evolveproCsvPath: "",
    evolveproMode: "pipeline",
  };
  const set = (update: Record<string, unknown> | ((current: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof update === "function" ? update(state) : update);
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

describe("annotateReferenceDomains", () => {
  beforeEach(() => {
    mockedSendRequest.mockReset();
  });

  it("stores reference-frame InterProScan domains", async () => {
    mockedSendRequest.mockResolvedValueOnce({
      domains: [{ name: "Catalytic domain", id: "IPR012345", start: 8, end: 54, db: "PFAM" }],
      source: "interproscan",
      coordinate_frame: "reference",
      protein_length: 60,
      ref_hash: "abc123",
      cache_hit: false,
    });
    const { state, slice } = makeStore();

    await slice.annotateReferenceDomains();

    expect(mockedSendRequest).toHaveBeenCalledWith(
      "annotate_domains_by_sequence",
      { sequence: expect.stringMatching(/^MKTAY/) },
      660_000,
    );
    expect(state.refDomains).toEqual([
      { name: "Catalytic domain", id: "IPR012345", start: 8, end: 54, db: "PFAM" },
    ]);
    expect(state.refDomainHash).toBe("abc123");
    expect(state.refDomainsLoading).toBe(false);
  });

  it("does not submit a sequence without external-service consent", async () => {
    const { slice } = makeStore(false);

    await slice.annotateReferenceDomains();

    expect(mockedSendRequest).not.toHaveBeenCalled();
  });

  it("preserves the last valid annotation when the service fails", async () => {
    mockedSendRequest.mockResolvedValueOnce({
      domains: [],
      source: "error",
      coordinate_frame: "reference",
      protein_length: 60,
      ref_hash: "",
      cache_hit: false,
      error_msg: "service unavailable",
    });
    const { state, slice } = makeStore();
    state.refDomains = [{ name: "Existing", id: "IPR1", start: 2, end: 20, db: "PFAM" }];
    state.refDomainHash = "existing-hash";

    await slice.annotateReferenceDomains();

    expect(state.refDomains).toEqual([
      { name: "Existing", id: "IPR1", start: 2, end: 20, db: "PFAM" },
    ]);
    expect(state.refDomainHash).toBe("existing-hash");
    expect(state.refDomainsLoading).toBe(false);
  });

  it("discards a response when the selected reference changes in flight", async () => {
    let resolveRequest: ((value: {
      domains: Array<{ name: string; id: string; start: number; end: number; db: string }>;
      source: "interproscan";
      coordinate_frame: "reference";
      protein_length: number;
      ref_hash: string;
      cache_hit: boolean;
    }) => void) | undefined;
    mockedSendRequest.mockImplementationOnce(() => new Promise((resolve) => {
      resolveRequest = resolve;
    }));
    const { state, slice } = makeStore();
    const pending = slice.annotateReferenceDomains();
    await vi.waitFor(() => expect(mockedSendRequest).toHaveBeenCalledOnce());
    state.seqInfo = {
      header: "changed",
      seq_length: 12,
      genes: [{
        gene: "changed",
        product: "changed",
        cds_start: 1,
        cds_end: 36,
        aa_length: 12,
        translation: "MABCDEFGHIJK",
      }],
    };
    resolveRequest?.({
      domains: [{ name: "Old", id: "IPR0", start: 1, end: 10, db: "PFAM" }],
      source: "interproscan",
      coordinate_frame: "reference",
      protein_length: 60,
      ref_hash: "old",
      cache_hit: false,
    });

    await pending;

    expect(state.refDomains).toEqual([]);
    expect(state.refDomainsLoading).toBe(false);
  });
});
