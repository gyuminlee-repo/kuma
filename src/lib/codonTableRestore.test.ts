/**
 * One test per row of the design note's section 8.3 table, each arranged so
 * that exactly one branch can fire.
 *
 * The mismatch row asserts the concrete amino acid list rather than that the
 * list is non-empty. Naming which amino acids moved is the whole reason that
 * branch refuses the design instead of shrugging, and a test that only counted
 * would pass on a resolver that returned every amino acid it knows.
 */
import { describe, expect, it } from "vitest";
import {
  blocksDesign,
  differingAminoAcids,
  resolveCodonTableRestore,
  type ExpectedCodonTable,
} from "./codonTableRestore";
import type { CodonTableDocument, OrganismSummary } from "@/types/models";

function doc(overrides: Partial<CodonTableDocument> = {}): CodonTableDocument {
  return {
    key: "mylab",
    name: "Lab strain",
    taxid: null,
    source: "test",
    genetic_code: 11,
    aliases: [],
    codons: {
      K: [["AAA", 0.76], ["AAG", 0.24]],
      L: [["CTG", 0.5], ["TTG", 0.5]],
      R: [["CGC", 0.6], ["CGT", 0.4]],
      M: [["ATG", 1.0]],
    },
    ...overrides,
  };
}

function organism(overrides: Partial<OrganismSummary> = {}): OrganismSummary {
  return {
    key: "mylab",
    name: "Lab strain",
    taxid: null,
    source: "user",
    aliases: [],
    cds_count: null,
    table_sha256: "aaa",
    warnings: [],
    normalizations: [],
    document: doc(),
    ...overrides,
  };
}

const expected = (o: Partial<ExpectedCodonTable> = {}): ExpectedCodonTable => ({
  key: "mylab",
  tableSha256: "aaa",
  ...o,
});

describe("section 8.3 restore branches", () => {
  it("row 1: installed and identical proceeds silently", () => {
    const state = resolveCodonTableRestore(expected(), [organism()]);
    expect(state).toEqual({ kind: "ok" });
    expect(blocksDesign(state)).toBe(false);
  });

  it("row 2: absent here but carried by the project offers an install", () => {
    const state = resolveCodonTableRestore(
      expected({ document: doc({ name: "Lab strain" }) }),
      [organism({ key: "ecoli", name: "E. coli", source: "builtin" })],
    );
    expect(state).toEqual({
      kind: "installable",
      key: "mylab",
      name: "Lab strain",
    });
    expect(blocksDesign(state)).toBe(true);
  });

  it("row 3: installed and different names the amino acids that moved", () => {
    const localDoc = doc({
      codons: {
        K: [["AAA", 0.76], ["AAG", 0.24]],
        // L and R moved; K and M did not.
        L: [["CTG", 0.9], ["TTG", 0.1]],
        R: [["CGT", 0.6], ["CGC", 0.4]],
        M: [["ATG", 1.0]],
      },
    });
    const state = resolveCodonTableRestore(
      expected({ tableSha256: "bbb", document: doc() }),
      [organism({ table_sha256: "aaa", document: localDoc })],
    );
    expect(state).toEqual({
      kind: "mismatch",
      key: "mylab",
      name: "Lab strain",
      differingAminoAcids: ["L", "R"],
      canInstall: true,
    });
    expect(blocksDesign(state)).toBe(true);
  });

  it("row 4: absent here with no copy keeps the key and blocks the design", () => {
    const state = resolveCodonTableRestore(expected(), [
      organism({ key: "ecoli", name: "E. coli", source: "builtin" }),
    ]);
    expect(state).toEqual({ kind: "absent", key: "mylab" });
    expect(blocksDesign(state)).toBe(true);
  });

  it("row 5: the project's copy is the authoritative one and is installable", () => {
    const state = resolveCodonTableRestore(
      expected({ tableSha256: "bbb", document: doc() }),
      [organism({ table_sha256: "aaa" })],
    );
    expect(state.kind).toBe("mismatch");
    // The offer exists, so the overwrite can be approved explicitly. Nothing
    // here performs it, and no branch rewrites the key.
    expect(state).toMatchObject({ canInstall: true, key: "mylab" });
  });
});

describe("the branches the two storage paths force apart", () => {
  it("a digest-only expectation cannot name amino acids and says so", () => {
    const state = resolveCodonTableRestore(expected({ tableSha256: "bbb" }), [
      organism({ table_sha256: "aaa" }),
    ]);
    expect(state).toEqual({
      kind: "mismatchUnexplained",
      key: "mylab",
      name: "Lab strain",
    });
    expect(blocksDesign(state)).toBe(true);
  });

  it("a bundled local table cannot be overwritten by an install (R5)", () => {
    const state = resolveCodonTableRestore(
      expected({ key: "ecoli", tableSha256: "bbb", document: doc({ key: "ecoli" }) }),
      [organism({ key: "ecoli", source: "builtin", table_sha256: "aaa" })],
    );
    expect(state).toMatchObject({ kind: "mismatch", canInstall: false });
  });

  it("an empty listing is 'not asked yet', never 'not installed'", () => {
    expect(resolveCodonTableRestore(expected(), [])).toEqual({ kind: "pending" });
  });

  it("a project that recorded no table restores exactly as before", () => {
    expect(resolveCodonTableRestore(null, [organism()])).toEqual({ kind: "ok" });
  });

  it("never rewrites the key to ecoli on any branch", () => {
    const states = [
      resolveCodonTableRestore(expected(), []),
      resolveCodonTableRestore(expected(), [organism({ key: "ecoli" })]),
      resolveCodonTableRestore(expected({ document: doc() }), [
        organism({ key: "ecoli" }),
      ]),
      resolveCodonTableRestore(expected({ tableSha256: "bbb" }), [organism()]),
    ];
    for (const state of states) {
      expect(JSON.stringify(state)).not.toContain("ecoli");
    }
  });
});

describe("differingAminoAcids", () => {
  it("is empty for two tables written in the same normalised order", () => {
    expect(differingAminoAcids(doc(), doc())).toEqual([]);
  });

  it("reports an amino acid one side does not have at all", () => {
    const missing = doc();
    delete missing.codons.M;
    expect(differingAminoAcids(doc(), missing)).toEqual(["M"]);
  });

  it("reports a reordering, because the digest is taken over that order", () => {
    const reordered = doc({
      codons: { ...doc().codons, K: [["AAG", 0.24], ["AAA", 0.76]] },
    });
    expect(differingAminoAcids(doc(), reordered)).toEqual(["K"]);
  });
});
