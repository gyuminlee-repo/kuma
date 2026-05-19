import { describe, expect, it } from "vitest";
import { getSortedMutations, reorderMappings } from "./plate-utils";
import type { PlateMapping, SdmPrimerResult } from "../types/models";

function result(mutation: string, aaPosition: number, penalty: number): SdmPrimerResult {
  return {
    mutation,
    aa_position: aaPosition,
    codon_pos: aaPosition * 3,
    forward_seq: "ATGC",
    reverse_seq: "GCAT",
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 3,
    has_offtarget: false,
    penalty,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "GTT",
    mt_codon: "TTT",
    overlap_seq: "ATGC",
    warnings: [],
  };
}

function mapping(mutation: string, primerType: PlateMapping["primer_type"], sequence: string): PlateMapping {
  return {
    well: "A1",
    primer_name: `${mutation}-${primerType}`,
    sequence,
    primer_type: primerType,
    mutation,
  };
}

describe("plate-utils", () => {
  it("keeps original tie order when sorting descending", () => {
    const results = [
      result("A1V", 1, 5),
      result("B2C", 2, 5),
      result("C3D", 3, 1),
    ];

    expect(getSortedMutations(results, [{ id: "penalty", desc: true }])).toEqual([
      "A1V",
      "B2C",
      "C3D",
    ]);
  });

  it("reorders forward mappings and paired reverse mappings by sorted mutation order", () => {
    const mappings = [
      mapping("A1V", "forward", "fwd-a"),
      mapping("B2C", "forward", "fwd-b"),
      mapping("C3D", "forward", "fwd-c"),
      mapping("A1V", "reverse", "rev-a"),
      mapping("B2C", "reverse", "rev-b"),
      mapping("C3D", "reverse", "rev-c"),
    ];
    const dedupInfo = {
      "rev-a": ["A1V"],
      "rev-b": ["B2C"],
      "rev-c": ["C3D"],
    };

    const ordered = reorderMappings(mappings, dedupInfo, ["C3D", "A1V", "B2C"]);

    expect(ordered.map((m) => `${m.primer_type}:${m.mutation}:${m.well}`)).toEqual([
      "forward:C3D:A1",
      "forward:A1V:B1",
      "forward:B2C:C1",
      "reverse:C3D:A1",
      "reverse:A1V:B1",
      "reverse:B2C:C1",
    ]);
  });
});
