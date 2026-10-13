/**
 * fetchStructure and annotateReferenceDomains write a progress line and then
 * drop their answer when the context they started from has moved on. The
 * newest call must not leave that progress line up for good, while an older
 * call stays silent (a newer one owns the line) and a line another action
 * wrote meanwhile is not removed.
 */
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
const STRUCTURE_LOADING = "AlphaFold structure loading...";
const SCANNING = "diversity.sequenceDomainScanning";

/** Each request of one method waits here until the test answers it. */
interface HeldRequest {
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
}
function holdRequests(heldMethod: string) {
  const held: HeldRequest[] = [];
  mockedSendRequest.mockImplementation(((method: string) => {
    if (method !== heldMethod) return Promise.reject(new Error(`unexpected ${method}`));
    return new Promise<unknown>((resolve, reject) => { held.push({ resolve, reject }); });
  }) as typeof sendRequest);
  return held;
}

const TRANSLATION = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQ";
const seqInfoFor = (translation: string) => ({
  header: "reference", seq_length: translation.length,
  genes: [{ gene: "target", product: "target protein", cds_start: 1, cds_end: 180,
    aa_length: translation.length, translation }],
});

function makeStore() {
  const state: Record<string, unknown> = {};
  const set = (update: Record<string, unknown> | ((current: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof update === "function" ? update(state) : update);
  };
  const get = () => state as unknown as AppState;
  const slice = createDiversitySlice(
    set as Parameters<typeof createDiversitySlice>[0],
    get as Parameters<typeof createDiversitySlice>[1],
    {} as Parameters<typeof createDiversitySlice>[2],
  );
  // Slice initial values go in first so the test values below win.
  Object.assign(state, slice, {
    seqInfo: seqInfoFor(TRANSLATION), selectedGene: "1", statusMessage: "Ready",
    uniprotAccession: "P12345", structureAccession: "",
    requireNetworkConsent: vi.fn(async () => true),
    requireContactEmail: vi.fn(async () => false),
    evolveproCsvPath: "", structuralDiversityEnabled: false, paretoDiversityEnabled: false,
    domainDiversityEnabled: false,
  });
  return { state, slice };
}

describe("fetchStructure status line when the accession changes under it", () => {
  beforeEach(() => { mockedSendRequest.mockReset(); });

  it("clears its loading line when the UniProt accession changes during the fetch", async () => {
    const held = holdRequests("fetch_structure");
    const { state, slice } = makeStore();
    const pending = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(held).toHaveLength(1));
    expect(state.statusMessage).toBe(STRUCTURE_LOADING);
    state.uniprotAccession = "Q50L36";
    held[0].resolve({ success: true, residues: 10 });
    await pending;
    expect(state.statusMessage).toBe("");
  });

  it("clears its loading line when the fetch fails after the accession changed", async () => {
    const held = holdRequests("fetch_structure");
    const { state, slice } = makeStore();
    const pending = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(held).toHaveLength(1));
    state.uniprotAccession = "Q50L36";
    held[0].reject(new Error("network down"));
    await pending;
    expect(state.statusMessage).toBe("");
  });

  it("leaves the line of a newer fetch alone when an older fetch is overtaken", async () => {
    const held = holdRequests("fetch_structure");
    const { state, slice } = makeStore();
    const older = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(held).toHaveLength(1));
    const newer = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(held).toHaveLength(2));
    held[0].resolve({ success: true, residues: 10 });
    await older;
    expect(state.statusMessage).toBe(STRUCTURE_LOADING);
    held[1].resolve({ success: true, residues: 10 });
    await newer;
    expect(state.statusMessage).toBe("AlphaFold structure loaded: 10 Cα residues");
  });

  it("does not remove a line another action wrote while the fetch was in flight", async () => {
    const held = holdRequests("fetch_structure");
    const { state, slice } = makeStore();
    const pending = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(held).toHaveLength(1));
    state.statusMessage = "Fetching domain info...";
    state.uniprotAccession = "Q50L36";
    held[0].resolve({ success: true, residues: 10 });
    await pending;
    expect(state.statusMessage).toBe("Fetching domain info...");
  });

  it("keeps the completion line when the accession did not change", async () => {
    const held = holdRequests("fetch_structure");
    const { state, slice } = makeStore();
    const pending = slice.fetchStructure("P12345");
    await vi.waitFor(() => expect(held).toHaveLength(1));
    held[0].resolve({ success: true, residues: 10 });
    await pending;
    expect(state.statusMessage).toBe("AlphaFold structure loaded: 10 Cα residues");
    expect(state.structureAccession).toBe("P12345");
  });
});

describe("annotateReferenceDomains status line when the sequence changes under it", () => {
  beforeEach(() => { mockedSendRequest.mockReset(); });
  const NO_DOMAINS = { domains: [], source: "interproscan", coordinate_frame: "reference",
    protein_length: TRANSLATION.length, ref_hash: "abc", cache_hit: false };

  it.each([
    ["the reference sequence is gone", () => null],
    ["the reference translation differs", () => seqInfoFor("MAAAAAAAAAAAAAAAA")],
  ])("clears its scanning line when %s", async (_label, nextSeqInfo) => {
    const held = holdRequests("annotate_domains_by_sequence");
    const { state, slice } = makeStore();
    const pending = slice.annotateReferenceDomains();
    await vi.waitFor(() => expect(held).toHaveLength(1));
    expect(state.statusMessage).toBe(SCANNING);
    state.seqInfo = nextSeqInfo();
    held[0].resolve(NO_DOMAINS);
    await pending;
    expect(state.statusMessage).toBe("");
    expect(state.refDomainsLoading).toBe(false);
  });

  it("leaves the line of a newer scan alone when an older scan is overtaken", async () => {
    const held = holdRequests("annotate_domains_by_sequence");
    const { state, slice } = makeStore();
    const older = slice.annotateReferenceDomains();
    await vi.waitFor(() => expect(held).toHaveLength(1));
    const newer = slice.annotateReferenceDomains();
    await vi.waitFor(() => expect(held).toHaveLength(2));
    state.seqInfo = null;
    held[0].resolve(NO_DOMAINS);
    await older;
    expect(state.statusMessage).toBe(SCANNING);
    held[1].resolve(NO_DOMAINS);
    await newer;
    expect(state.statusMessage).toBe("");
  });

  it("does not remove a line another action wrote while the scan was in flight", async () => {
    const held = holdRequests("annotate_domains_by_sequence");
    const { state, slice } = makeStore();
    const pending = slice.annotateReferenceDomains();
    await vi.waitFor(() => expect(held).toHaveLength(1));
    state.statusMessage = "Sequence file loaded";
    state.seqInfo = null;
    held[0].resolve(NO_DOMAINS);
    await pending;
    expect(state.statusMessage).toBe("Sequence file loaded");
  });

  it("keeps the completion line when the sequence did not change", async () => {
    const held = holdRequests("annotate_domains_by_sequence");
    const { state, slice } = makeStore();
    const pending = slice.annotateReferenceDomains();
    await vi.waitFor(() => expect(held).toHaveLength(1));
    held[0].resolve(NO_DOMAINS);
    await pending;
    expect(state.statusMessage).toBe("diversity.sequenceDomainsNone");
  });
});
