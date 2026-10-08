import { describe, expect, it } from "vitest";
import type { PlateMapping, SdmPrimerResult } from "@/types/models";
import { wellName } from "@/lib/plate-utils";
import { buildResultWellMap } from "./resultTableWells";

function primer(position: number, overrides: Partial<SdmPrimerResult> = {}): SdmPrimerResult {
  return {
    mutation: `M${position}A`, aa_position: position, codon_pos: 0,
    forward_seq: `F${position}`, reverse_seq: `R${position}`,
    fwd_len: 20, rev_len: 20, overlap_len: 18, tm_no_fwd: 62, tm_no_rev: 58,
    tm_overlap: 42, tm_condition_met: true, tolerance_used: 1, has_offtarget: false,
    penalty: 0, gc_fwd: 50, gc_rev: 50, wt_codon: "ATG", mt_codon: "GCG",
    overlap_seq: "ATGC", warnings: [], ...overrides,
  };
}
function forward(result: SdmPrimerResult, well: string): PlateMapping {
  return { mutation: result.mutation, sequence: result.forward_seq,
    primer_name: `${result.mutation}_F`, primer_type: "forward", well };
}

describe("result-table export well identity", () => {
  it("uses the stored forward mapping rather than the result-array position when unsorted", () => {
    const results = [primer(3), primer(1), primer(2)];
    const mappings = [forward(results[1], "A1"), forward(results[2], "B1"), forward(results[0], "H12")];
    const wells = buildResultWellMap(results, mappings, {}, []);
    expect(results.map((r) => wells.get(r))).toEqual(["H12", "A01", "B01"]);
    expect(mappings.map((m) => m.well)).toEqual(["A1", "B1", "H12"]);
  });

  it.each([false, true])("follows canonical export sorting, desc=%s", (desc) => {
    const results = [primer(3), primer(1), primer(2)];
    const mappings = results.map((r, i) => forward(r, wellName(i)));
    const wells = buildResultWellMap(results, mappings, {}, [{ id: "mutation", desc }]);
    expect(results.map((r) => wells.get(r))).toEqual(desc
      ? ["A01", "C01", "B01"]
      : ["C01", "A01", "B01"]);
  });

  it("keeps identities through display-only reorder, filtering and page windows", () => {
    const results = Array.from({ length: 100 }, (_, i) => primer(i + 1));
    const mappings = results.map((r, i) => forward(r, wellName(i)));
    const wells = buildResultWellMap(results, mappings, {}, []);
    const filteredPage = [...results].reverse().filter((r) => (r.aa_position ?? 0) % 2 === 0).slice(1, 3);
    expect(filteredPage.map((r) => [r.mutation, wells.get(r)])).toEqual([
      ["M98A", "R2: B01"], ["M96A", "R1: H12"],
    ]);
    expect(wells.get(results[0])).toBe("R1: A01");
  });

  it.each([95, 96, 97, 191, 192, 193, 288, 289])("matches round layout at %i results", (count) => {
    const results = Array.from({ length: count }, (_, i) => primer(i + 1));
    const wells = buildResultWellMap(results, results.map((r, i) => forward(r, wellName(i))), {}, []);
    expect(wells.size).toBe(count);
    for (const [index, result] of results.entries()) {
      const local = index % 96;
      const expected = `${"ABCDEFGH"[local % 8]}${String(Math.floor(local / 8) + 1).padStart(2, "0")}`;
      expect(wells.get(result)).toBe(count > 96 ? `R${Math.floor(index / 96) + 1}: ${expected}` : expected);
    }
  });

  it("restarts the next round only when canonical export order crosses its boundary", () => {
    const results = Array.from({ length: 97 }, (_, i) => primer(i + 1));
    const wells = buildResultWellMap(results, results.map((r, i) => forward(r, wellName(i))), {}, [{ id: "mutation", desc: true }]);
    expect(wells.get(results[96])).toBe("R1: A01");
    expect(wells.get(results[1])).toBe("R1: H12");
    expect(wells.get(results[0])).toBe("R2: A01");
  });

  it("labels only the selected candidate matching the exported primer sequence", () => {
    const oldCandidate = primer(1);
    const chosen = primer(1, { forward_seq: "CHOSEN" });
    const wells = buildResultWellMap([oldCandidate, chosen], [forward(chosen, "C7")], {}, []);
    expect(wells.get(chosen)).toBe("C07");
    expect(wells.has(oldCandidate)).toBe(false);
  });

  it("does not confuse a deduplicated reverse well with its forward identity", () => {
    const result = primer(1);
    const reverse: PlateMapping = { ...forward(result, "A1"), sequence: result.reverse_seq, primer_type: "reverse" };
    expect(buildResultWellMap([result], [reverse, forward(result, "H12")], {}, []).get(result)).toBe("H12");
  });

  it("does not manufacture wells for empty, unmapped, invalid or ambiguous results", () => {
    const result = primer(1);
    expect(buildResultWellMap([], [], {}, []).size).toBe(0);
    expect(buildResultWellMap([result], [], {}, []).size).toBe(0);
    expect(buildResultWellMap([result], [forward(result, "A13")], {}, []).size).toBe(0);
    expect(buildResultWellMap([result], [forward(result, "A1"), forward(result, "B1")], {}, []).size).toBe(0);
  });
});
