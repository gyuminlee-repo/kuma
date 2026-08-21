import { describe, expect, it } from "vitest";
import type { SdmPrimerResult } from "../../types/models";
import { applyReversePropagation } from "./designSlice.helpers";

/**
 * Mutations at one amino-acid position share a reverse primer, so swapping one
 * rewrites the others. The backend does this in `_apply_direction_swap`, but
 * `swap_primer` replies with the clicked mutation alone, so the store repeats
 * it for the rows it already holds. Until v0.16.34 the store carried four of
 * those fields, and the neighbour rows on screen kept the hairpin, homodimer,
 * synthesis and tolerance numbers of a reverse primer that had been replaced,
 * while the exported workbook, built from backend state, carried others.
 *
 * The field NAMES are also pinned from the Python side, in
 * `tests/sidecar_kuro/test_swap_primer_fields.py`, which reads this module as
 * text. That test runs in CI; this one covers the arithmetic that a text scan
 * cannot see.
 */

function primer(overrides: Partial<SdmPrimerResult> = {}): SdmPrimerResult {
  return {
    mutation: "V371W",
    aa_position: 371,
    codon_pos: 1110,
    forward_seq: "ATGCATGCATGCATGCATGC",
    reverse_seq: "GCATGCATGCATGCATGCAT",
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 0.5,
    tolerance_fwd: 0.5,
    tolerance_rev: 0.5,
    has_offtarget: false,
    penalty: 1,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "GTT",
    mt_codon: "TGG",
    overlap_seq: "ATGCATGCATGCATGCAT",
    warnings: [],
    ...overrides,
  };
}

const incoming = primer({
  mutation: "V371L",
  reverse_seq: "TTTTGCATGCATGCATGCAT",
  rev_len: 21,
  tm_no_rev: 61.5,
  gc_rev: 45,
  tolerance_rev: 3.5,
  synthesis_score_rev: 44,
  hairpin_tm_rev: 72.5,
  hairpin_dg_rev: -9.25,
  homodimer_tm_rev: 65.5,
  homodimer_dg_rev: -7.75,
  warnings: ["Rev synthesis score 44/100 (difficult)", "Fwd hairpin Tm=71.5C"],
});

describe("applyReversePropagation", () => {
  it("carries every reverse diagnostic, not only the sequence and its Tm", () => {
    const merged = applyReversePropagation(primer(), incoming);

    expect(merged.reverse_seq).toBe(incoming.reverse_seq);
    expect(merged.rev_len).toBe(incoming.rev_len);
    expect(merged.tm_no_rev).toBe(incoming.tm_no_rev);
    expect(merged.gc_rev).toBe(incoming.gc_rev);
    expect(merged.tolerance_rev).toBe(3.5);
    expect(merged.synthesis_score_rev).toBe(44);
    expect(merged.hairpin_tm_rev).toBe(72.5);
    expect(merged.hairpin_dg_rev).toBe(-9.25);
    expect(merged.homodimer_tm_rev).toBe(65.5);
    expect(merged.homodimer_dg_rev).toBe(-7.75);
  });

  it("leaves the forward primer of the neighbour alone", () => {
    const neighbour = primer({ hairpin_tm_fwd: 30, synthesis_score_fwd: 90 });
    const merged = applyReversePropagation(neighbour, incoming);

    expect(merged.forward_seq).toBe(neighbour.forward_seq);
    expect(merged.tm_no_fwd).toBe(neighbour.tm_no_fwd);
    expect(merged.hairpin_tm_fwd).toBe(30);
    expect(merged.synthesis_score_fwd).toBe(90);
  });

  it("re-derives has_offtarget from both directions", () => {
    const hit = {
      position: 42,
      strand: "sense" as const,
      match_seq: "ACGTACGTACGT",
      tm: 55.5,
      match_length: 12,
    };
    const withHit = applyReversePropagation(
      primer(),
      primer({ ...incoming, offtarget_rev: [hit] }),
    );
    expect(withHit.has_offtarget).toBe(true);

    const cleared = applyReversePropagation(
      primer({ has_offtarget: true, offtarget_rev: [hit] }),
      incoming,
    );
    expect(cleared.has_offtarget).toBe(false);

    const keptFromForward = applyReversePropagation(
      primer({ has_offtarget: true, offtarget_fwd: [hit] }),
      incoming,
    );
    expect(keptFromForward.has_offtarget).toBe(true);
  });

  it("does not share the hit list with the primer it came from", () => {
    const hit = {
      position: 7,
      strand: "antisense" as const,
      match_seq: "TTTT",
      tm: 40,
      match_length: 4,
    };
    const source = primer({ ...incoming, offtarget_rev: [hit] });
    const merged = applyReversePropagation(primer(), source);

    expect(merged.offtarget_rev).toEqual(source.offtarget_rev);
    expect(merged.offtarget_rev).not.toBe(source.offtarget_rev);
  });

  it("raises tolerance_used to the incoming reverse step and never lowers it", () => {
    const raised = applyReversePropagation(primer(), incoming);
    expect(raised.tolerance_used).toBe(3.5);

    const gentle = applyReversePropagation(
      primer({ tolerance_used: 4, tolerance_fwd: 4 }),
      incoming,
    );
    expect(gentle.tolerance_used).toBe(4);
  });

  it("takes the reverse warnings and keeps the forward ones", () => {
    const neighbour = primer({
      warnings: [
        "Fwd hairpin Tm=48.9C",
        "Rev length 20 nt is below KOD recommended 22-35 nt",
        "Reverse primer too long: 61 bp",
      ],
    });
    const merged = applyReversePropagation(neighbour, incoming);

    expect(merged.warnings).toContain("Fwd hairpin Tm=48.9C");
    expect(merged.warnings).toContain("Rev synthesis score 44/100 (difficult)");
    expect(merged.warnings).not.toContain(
      "Rev length 20 nt is below KOD recommended 22-35 nt",
    );
    expect(merged.warnings).not.toContain("Reverse primer too long: 61 bp");
    // A forward warning belonging to the incoming primer is not this row's.
    expect(merged.warnings).not.toContain("Fwd hairpin Tm=71.5C");
  });

  it("does not mutate the row it was given", () => {
    const neighbour = primer();
    const before = JSON.stringify(neighbour);
    applyReversePropagation(neighbour, incoming);
    expect(JSON.stringify(neighbour)).toBe(before);
  });
});
