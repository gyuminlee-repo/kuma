/**
 * After a UniProt search the slice asks the AlphaFold server which candidates
 * have a structure, to badge them. That is a request to a second service, so
 * UniProt consent does not cover it: it goes out only when AlphaFold is already
 * permitted (online, switched on, listed in the grant). It is a background
 * extra, so it never opens the consent dialog either.
 */
import { describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { sendRequest } from "../../lib/ipc-kuro";
import { createDiversitySlice } from "./diversitySlice";

vi.mock("../../lib/ipc-kuro", () => ({ sendRequest: vi.fn() }));
vi.mock("i18next", () => ({ default: { t: (key: string) => key } }));

const mocked = vi.mocked(sendRequest);

function makeStore(overrides: Record<string, unknown>) {
  const state: Record<string, unknown> = {
    offlineMode: false,
    networkConsentGranted: true,
    networkConsentServices: ["uniprot", "blast", "alphafold", "interpro"],
    isNetworkServiceEnabled: () => true,
    requireNetworkConsent: vi.fn(async () => true),
    requireContactEmail: vi.fn(async () => false),
    fetchDomains: vi.fn(async () => undefined),
    structureAccession: "",
    statusMessage: "",
    ...overrides,
  };
  const set = (update: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof update === "function" ? update(state) : update);
  };
  const slice = createDiversitySlice(
    set as Parameters<typeof createDiversitySlice>[0],
    (() => state as unknown as AppState) as Parameters<typeof createDiversitySlice>[1],
    {} as Parameters<typeof createDiversitySlice>[2],
  );
  Object.assign(state, slice);
  return state as unknown as AppState & Record<string, unknown>;
}

async function searchAndSettle(store: AppState) {
  mocked.mockReset();
  mocked.mockImplementation((async (method: string) => method === "search_uniprot"
    ? { candidates: [{ accession: "P00001", identity: 99 }], auto_selected: "" }
    : { availability: { P00001: true } }) as unknown as typeof sendRequest);
  // The probe is either sent or refused synchronously inside searchUniprot,
  // so its decision is final once the search resolves.
  await store.searchUniprot("gene", "org", "", "");
  return mocked.mock.calls.some(([method]) => method === "check_structures_available");
}

describe("AlphaFold structure badge probe", () => {
  it("asks AlphaFold and badges the candidates when AlphaFold is permitted", async () => {
    const store = makeStore({});
    expect(await searchAndSettle(store)).toBe(true);
    await vi.waitFor(() =>
      expect(store.uniprotCandidates[0]).toMatchObject({ accession: "P00001", has_structure: true }));
  });

  it.each([
    ["AlphaFold is switched off", { isNetworkServiceEnabled: (s: string) => s !== "alphafold" }],
    ["the grant did not list AlphaFold", { networkConsentServices: ["uniprot", "blast"] }],
    ["nothing was granted", { networkConsentGranted: false }],
  ])("does not ask AlphaFold when %s", async (_why, overrides) => {
    const store = makeStore(overrides);
    expect(await searchAndSettle(store)).toBe(false);
    expect(store.requireNetworkConsent).not.toHaveBeenCalledWith("alphafold");
  });
});
