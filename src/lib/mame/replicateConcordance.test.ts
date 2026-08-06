/**
 * What the flags have to get right, stated as the cases that separate the
 * chosen rule from a plausible wrong one.
 *
 * The pivot key is the well, not the variant. The depth rule is a ratio, not an
 * absolute read floor, and the two disagree in both directions. And a run that
 * cannot state which plates it scored gets `null` for missing_replicate rather
 * than a `false` that reads as "checked, nothing missing".
 */

import { describe, expect, it } from "vitest";
import type { VerdictRecord } from "@/types/mame/models";
import {
  DEPTH_IMBALANCE_MIN_RATIO,
  computeReplicateConcordance,
} from "./replicateConcordance";

function verdict(
  plate: string,
  well: string,
  mutantId: string,
  overrides: Partial<VerdictRecord> = {},
): VerdictRecord {
  return {
    native_barcode: plate,
    custom_barcode: well,
    file_size_kb: 100,
    read_count: 1000,
    n_mixed_positions: 0,
    max_minor_allele_fraction: 0,
    n_low_depth_positions: 0,
    consensus_n_fraction: 0,
    n_low_quality_bases: 0,
    n_input_reads: 1000,
    n_aligned_reads: 990,
    n_mapq_failed: 0,
    n_span_failed: 0,
    source_path: `/demux/${plate}/${well}.fasta`,
    aa_sequence: "MK",
    observed_nt_changes: [],
    observed_aa_changes: [],
    n_no_call_aa: 0,
    expected_mutations: [],
    mutant_id: mutantId,
    verdict: "PASS",
    verdict_notes: "",
    ...overrides,
  };
}

const TWO_PLATES = ["sort_barcode07", "sort_barcode08"];

describe("computeReplicateConcordance, pivot key", () => {
  it("pivots on the well, so two wells holding one variant stay two rows", () => {
    // Six records, three wells, two plates. The last well is the one where the
    // copies were assigned different variant ids: a mutant_id pivot would fold
    // it into the M1 group and report two rows instead of three.
    const verdicts = [
      verdict("sort_barcode07", "1_1", "M1"),
      verdict("sort_barcode08", "1_1", "M1"),
      verdict("sort_barcode07", "2_1", "M1"),
      verdict("sort_barcode08", "2_1", "M1"),
      verdict("sort_barcode07", "3_1", "M1"),
      verdict("sort_barcode08", "3_1", "M2"),
    ];

    const result = computeReplicateConcordance(verdicts, TWO_PLATES);

    expect(result.wells).toHaveLength(3);
    expect(result.wells.map((w) => w.well)).toEqual(["1_1", "2_1", "3_1"]);
    for (const well of result.wells) {
      expect(well.presentPlates).toEqual(TWO_PLATES);
      expect(well.missingReplicate).toBe(false);
    }
  });

  it("flags a well whose plate copies were called differently", () => {
    const verdicts = [
      verdict("sort_barcode07", "1_1", "M1"),
      verdict("sort_barcode08", "1_1", "M1", { verdict: "WRONG_AA" }),
      verdict("sort_barcode07", "2_1", "M2"),
      verdict("sort_barcode08", "2_1", "M2"),
    ];

    const byWell = computeReplicateConcordance(verdicts, TWO_PLATES).byWell;

    expect(byWell.get("1_1")?.verdictDisagreement).toBe(true);
    expect(byWell.get("2_1")?.verdictDisagreement).toBe(false);
  });
});

describe("computeReplicateConcordance, depth rule", () => {
  function depths(a: number, b: number) {
    return computeReplicateConcordance(
      [
        verdict("sort_barcode07", "1_1", "M1", { read_count: a }),
        verdict("sort_barcode08", "1_1", "M1", { read_count: b }),
      ],
      TWO_PLATES,
    ).byWell.get("1_1");
  }

  it("uses the ratio, not an absolute read floor: 10 vs 40 reads is not flagged", () => {
    // Proportionate but shallow. A "min < 30 reads" rule would flag this one;
    // the ratio rule does not, because the copies remain comparable.
    const well = depths(10, 40);
    expect(well?.depthRatio).toBeCloseTo(0.25, 10);
    expect(well?.depthImbalance).toBe(false);
  });

  it("uses the ratio, not an absolute read floor: 100 vs 1000 reads is flagged", () => {
    // Deep but lopsided, the opposite answer from the same floor rule.
    const well = depths(100, 1000);
    expect(well?.depthRatio).toBeCloseTo(0.1, 10);
    expect(well?.depthImbalance).toBe(true);
  });

  it("does not flag a copy sitting exactly on the threshold", () => {
    expect(DEPTH_IMBALANCE_MIN_RATIO).toBe(0.2);
    const well = depths(200, 1000);
    expect(well?.depthRatio).toBeCloseTo(0.2, 10);
    expect(well?.depthImbalance).toBe(false);
  });

  it("flags the first step below the threshold", () => {
    const well = depths(199, 1000);
    expect(well?.depthImbalance).toBe(true);
  });

  it("leaves a copy that reported no read count out of the comparison", () => {
    const well = computeReplicateConcordance(
      [
        verdict("sort_barcode07", "1_1", "M1", { read_count: null }),
        verdict("sort_barcode08", "1_1", "M1", { read_count: 1000 }),
      ],
      TWO_PLATES,
    ).byWell.get("1_1");

    expect(well?.depthRatio).toBeNull();
    expect(well?.depthImbalance).toBe(false);
  });
});

describe("computeReplicateConcordance, missing replicate", () => {
  it("names the plate a well is missing from", () => {
    const well = computeReplicateConcordance(
      [verdict("sort_barcode07", "1_1", "M1")],
      TWO_PLATES,
    ).byWell.get("1_1");

    expect(well?.missingReplicate).toBe(true);
    expect(well?.missingPlates).toEqual(["sort_barcode08"]);
  });

  it("reports the flag as undecidable when the run cannot state its plates", () => {
    // Consensus-directory path: the other two flags still compute.
    const result = computeReplicateConcordance(
      [
        verdict("sort_barcode07", "1_1", "M1", { read_count: 100 }),
        verdict("sort_barcode08", "1_1", "M1", { read_count: 1000, verdict: "WRONG_AA" }),
      ],
      null,
    );
    const well = result.byWell.get("1_1");

    expect(result.platesKnown).toBe(false);
    expect(well?.missingReplicate).toBeNull();
    expect(well?.missingPlates).toEqual([]);
    expect(well?.verdictDisagreement).toBe(true);
    expect(well?.depthImbalance).toBe(true);
  });

  it("stays undecidable for a single-plate run: nothing to be missing from", () => {
    const result = computeReplicateConcordance(
      [verdict("sort_barcode07", "1_1", "M1")],
      ["sort_barcode07"],
    );

    expect(result.platesKnown).toBe(false);
    expect(result.byWell.get("1_1")?.missingReplicate).toBeNull();
  });

  it("does not misread a plate named by its MinKNOW dir instead of its sort name", () => {
    // The regression this exists for: `detect` reports both `barcode07` and
    // `sort_barcode07`, and the records carry the sort name (the demux output
    // directory). Passing the MinKNOW dir names here marks every well missing.
    const verdicts = [
      verdict("sort_barcode07", "1_1", "M1"),
      verdict("sort_barcode08", "1_1", "M1"),
    ];

    expect(
      computeReplicateConcordance(verdicts, TWO_PLATES).byWell.get("1_1")
        ?.missingReplicate,
    ).toBe(false);
    expect(
      computeReplicateConcordance(verdicts, ["barcode07", "barcode08"]).byWell.get(
        "1_1",
      )?.missingReplicate,
    ).toBe(true);
  });
});
