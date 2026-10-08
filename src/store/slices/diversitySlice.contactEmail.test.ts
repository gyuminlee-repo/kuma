/**
 * BLAST and InterProScan go to EBI Job Dispatcher, which needs the user's own
 * contact email. With none configured the sidecar skips the submission and
 * answers `error_code: "contact_email_required"`. The slice must then ask for
 * an address (after network consent, never before), retry once when one is
 * given, and carry on without the EBI step when the user declines.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import type { AnnotateDomainsResult, SearchUniprotResult } from "../../types/models";
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

/** Answer every RPC from one function, whatever its declared result type. */
function respond(answer: (method: string) => unknown) {
  mockedSendRequest.mockImplementation(
    ((method: string) => Promise.resolve(answer(method))) as typeof sendRequest,
  );
}

const TRANSLATION = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQ";

function makeStore(emailGiven: boolean) {
  const order: string[] = [];
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
        translation: TRANSLATION,
      }],
    },
    selectedGene: "1",
    offlineMode: false,
    statusMessage: "",
    structureAccession: "",
    requireNetworkConsent: vi.fn(async () => {
      order.push("consent");
      return true;
    }),
    requireContactEmail: vi.fn(async () => {
      order.push("email");
      return emailGiven;
    }),
    isNetworkServiceEnabled: () => true,
    loadEvolveproCsv: vi.fn().mockResolvedValue(undefined),
    fetchDomains: vi.fn().mockResolvedValue(undefined),
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
  return { state, slice, order };
}

const EMAIL_REQUIRED_SEARCH: SearchUniprotResult = {
  candidates: [],
  auto_selected: null,
  error_detail: null,
  error_code: "contact_email_required",
};

const BLAST_HIT = {
  accession: "P12345",
  name: "target",
  organism: "E. coli",
  length: 60,
  identity: 99.0,
};

function uniprotCalls() {
  return mockedSendRequest.mock.calls.filter(([method]) => method === "search_uniprot");
}

describe("searchUniprot without a contact email", () => {
  beforeEach(() => mockedSendRequest.mockReset());

  it("asks for an email after consent and retries the search once it is given", async () => {
    respond((method: string) => {
      if (method === "search_uniprot") {
        return uniprotCalls().length === 1
          ? EMAIL_REQUIRED_SEARCH
          : { candidates: [BLAST_HIT], auto_selected: "P12345", error_detail: null };
      }
      return { availability: {} };
    });
    const { state, slice, order } = makeStore(true);

    await slice.searchUniprot("target", "E. coli", TRANSLATION, "");

    // Consent first, then the address. Later entries are the AlphaFold
    // availability check that follows a successful search.
    expect(order.slice(0, 2)).toEqual(["consent", "email"]);
    expect(uniprotCalls()).toHaveLength(2);
    expect(state.uniprotAccession).toBe("P12345");
    expect(state.uniprotSearching).toBe(false);
  });

  it("keeps the other lookups and says BLAST was skipped when the user declines", async () => {
    respond((method: string) => {
      if (method === "search_uniprot") return EMAIL_REQUIRED_SEARCH;
      return { availability: {} };
    });
    const { state, slice } = makeStore(false);

    await slice.searchUniprot("target", "E. coli", TRANSLATION, "");

    expect(uniprotCalls()).toHaveLength(1);
    expect(state.uniprotSearching).toBe(false);
    expect(String(state.statusMessage)).toContain("contactEmail.blastSkipped");
  });

  it("does not ask when the sidecar had an address", async () => {
    respond((method: string) => {
      if (method === "search_uniprot") {
        return { candidates: [BLAST_HIT], auto_selected: "P12345", error_detail: null };
      }
      return { availability: {} };
    });
    const { state, slice } = makeStore(true);

    await slice.searchUniprot("target", "E. coli", TRANSLATION, "");

    expect(state.requireContactEmail).not.toHaveBeenCalled();
    expect(uniprotCalls()).toHaveLength(1);
  });
});

const EMAIL_REQUIRED_SCAN: AnnotateDomainsResult = {
  domains: [],
  protein_length: 60,
  source: "error",
  coordinate_frame: "reference",
  ref_hash: "abc",
  cache_hit: false,
  error_msg: "A contact email is required to submit to InterProScan",
  error_code: "contact_email_required",
};

describe("annotateReferenceDomains without a contact email", () => {
  beforeEach(() => mockedSendRequest.mockReset());

  it("asks after consent, then resumes the scan with the saved address", async () => {
    mockedSendRequest
      .mockResolvedValueOnce(EMAIL_REQUIRED_SCAN)
      .mockResolvedValueOnce({
        domains: [{ name: "Catalytic", id: "IPR012345", start: 8, end: 54, db: "PFAM" }],
        source: "interproscan",
        coordinate_frame: "reference",
        protein_length: 60,
        ref_hash: "abc",
        cache_hit: false,
      });
    const { state, slice, order } = makeStore(true);

    await slice.annotateReferenceDomains();

    expect(order).toEqual(["consent", "email"]);
    expect(mockedSendRequest).toHaveBeenCalledTimes(2);
    expect(state.refDomains).toHaveLength(1);
    expect(state.refDomainsLoading).toBe(false);
  });

  it("skips the scan with a status message when the user declines", async () => {
    mockedSendRequest.mockResolvedValueOnce(EMAIL_REQUIRED_SCAN);
    const { state, slice } = makeStore(false);

    await slice.annotateReferenceDomains();

    expect(mockedSendRequest).toHaveBeenCalledTimes(1);
    expect(state.refDomainsLoading).toBe(false);
    expect(String(state.statusMessage)).toContain("contactEmail.interproSkipped");
  });
});
