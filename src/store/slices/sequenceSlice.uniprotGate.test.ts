import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createSequenceSlice } from "./sequenceSlice";

// searchUniprot itself is deep in diversitySlice.ts (its behavior is frozen
// scope). Only the gate that decides whether to call it is under test here.
function makeStore(overrides: Partial<AppState> = {}) {
  const fixture: Record<string, unknown> = {
    seqInfo: {
      genes: [
        {
          gene: "ispS",
          cds_start: 1,
          aa_length: 10,
          organism: "e_coli",
          translation: "MKT",
          uniprot_accession: "",
        },
      ],
    },
    organism: "e_coli",
    selectedGene: "1",
    domainDiversityEnabled: false,
    paretoDiversityEnabled: false,
    structuralDiversityEnabled: false,
    statusMessage: "",
    searchUniprot: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const state: Record<string, unknown> = { ...fixture };
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u);
  };
  const get = () => state as unknown as AppState;
  const slice = createSequenceSlice(
    set as Parameters<typeof createSequenceSlice>[0],
    get as Parameters<typeof createSequenceSlice>[1],
    {} as Parameters<typeof createSequenceSlice>[2],
  );
  // createSequenceSlice's own initial state (seqInfo: null, etc.) would
  // otherwise clobber the fixture set above, apply slice first, then
  // re-assert the fixture so test data always wins over slice defaults.
  Object.assign(state, slice, fixture);
  return { state, slice };
}

describe("setSelectedGene uniprot auto-search gate", () => {
  beforeEach(() => vi.clearAllMocks());

  it("skips searchUniprot when no known accession and all diversity consumers are off", () => {
    const { state, slice } = makeStore();
    slice.setSelectedGene("1");
    expect(state.searchUniprot).not.toHaveBeenCalled();
    expect(state.statusMessage).toMatch(/skipped/i);
  });

  it("calls searchUniprot when no known accession but domainDiversityEnabled is on", () => {
    const { state, slice } = makeStore({ domainDiversityEnabled: true } as Partial<AppState>);
    slice.setSelectedGene("1");
    expect(state.searchUniprot).toHaveBeenCalledTimes(1);
  });

  it("calls searchUniprot when a known accession exists, even with all diversity consumers off", () => {
    const { state, slice } = makeStore({
      seqInfo: {
        genes: [
          {
            gene: "ispS",
            cds_start: 1,
            aa_length: 10,
            organism: "e_coli",
            translation: "MKT",
            uniprot_accession: "P0CJ90",
          },
        ],
      },
    } as Partial<AppState>);
    slice.setSelectedGene("1");
    expect(state.searchUniprot).toHaveBeenCalledTimes(1);
    expect(state.searchUniprot).toHaveBeenCalledWith("ispS", "e_coli", "MKT", "P0CJ90");
  });
});
