/**
 * The declared types accept what the Python producers actually return.
 *
 * Every fixture below is annotated with the TS type it claims to be, so `tsc`
 * refuses the file if a type omits a key the sidecar sends or forbids a shape
 * it can produce. That is the point: these cases are latent at runtime (no
 * consumer reads the fields yet), so a plain runtime assertion would pass
 * against the broken types. The type annotation is the assertion; the runtime
 * expectations below it keep the fixtures from being dead code.
 *
 * Ground truth is the Python source in every case, cited per fixture.
 */

import { describe, expect, it } from "vitest";

import { methodLabelOf } from "@/components/mame/panels/ParameterPanel";
import type { CombinatorialDemuxStats } from "./combinatorial_demux";
import type { AnalyzeResult, DistributionStats } from "./models";
import type { ThresholdKind } from "./run_quality";
import type {
  EvolveproLoadResult,
  ExportMappingResult,
  ExportOrderResult,
  ExportResult,
} from "@/types/models";

describe("ThresholdKind covers what serialise_run_quality emits", () => {
  it("admits the self_set kind the reference_edge threshold carries", () => {
    // kuma_core/mame/run_quality.py:612 emits this literal unconditionally.
    const kind: ThresholdKind = "self_set";
    expect(kind).toBe("self_set");
  });

  it("still admits the four sourced kinds", () => {
    const kinds: ThresholdKind[] = [
      "vendor_default",
      "vendor_recommendation",
      "literature",
      "vendor_warranty",
    ];
    expect(kinds).toHaveLength(4);
  });
});

describe("DistributionStats admits the empty-input response", () => {
  it("accepts the exact object compute_distribution_stats([]) produces", () => {
    // kuma_core/mame/distribution.py:119-120 returns DistributionStats(n_files=0),
    // leaving file_size_kb at its field(default_factory=dict) default, and
    // python-core/sidecar_mame/handlers/analyze.py:2244 forwards it verbatim.
    // Reachable because the empty-records raise at analyze.py:1912 is gated on
    // `is_raw`, so a pre-demuxed consensus dir with no consensus FASTA gets here.
    const empty: DistributionStats = {
      n_files: 0,
      file_size_kb: {},
      suggested_cutoff_kb: 50.0,
      suggested_method: "fixed_50",
      bimodal: false,
    };
    expect(Object.keys(empty.file_size_kb)).toHaveLength(0);
  });

  it("still accepts the fully populated object", () => {
    // distribution.py:132-142 builds all nine keys unconditionally, so a
    // populated file_size_kb is never partial.
    const full: DistributionStats = {
      n_files: 12,
      file_size_kb: {
        min: 41.0,
        p05: 44.2,
        p25: 51.5,
        median: 60.0,
        p75: 71.2,
        p95: 88.0,
        max: 91.5,
        mean: 62.1,
        std: 13.4,
      },
      suggested_cutoff_kb: 51.5,
      suggested_method: "p05",
      bimodal: false,
    };
    expect(full.file_size_kb.median).toBe(60.0);
  });
});

describe("the recommended-cutoff sentence never prints undefined", () => {
  it("phrases every method distribution.py can assign", () => {
    // distribution.py:42,149,153,156,162 are the only assignment sites.
    expect(methodLabelOf("kneedle")).toBe("knee");
    expect(methodLabelOf("p05")).toBe("p05");
    expect(methodLabelOf("median_minus_2sigma")).toBe("median − 2σ");
    expect(methodLabelOf("fixed_50")).toBe("floor 50");
  });

  it("falls back to the raw name for a method it has no phrase for", () => {
    // A Python Literal is not enforced at runtime, so a sidecar of a different
    // build can still send a fifth value. The old code indexed to `undefined`
    // and interpolated that word into the sentence.
    const fromAnotherBuild = "otsu" as DistributionStats["suggested_method"];
    expect(methodLabelOf(fromAnotherBuild)).toBe("otsu");
    expect(methodLabelOf(fromAnotherBuild)).not.toBeUndefined();
  });
});

describe("AnalyzeResult keeps the barcode prefix provenance", () => {
  it("accepts the block as BarcodePrefixResolution.as_dict builds it", () => {
    // kuma_core/mame/ingest/combinatorial_demux.py:487-493 and :443-452, spread
    // onto the response at python-core/sidecar_mame/handlers/analyze.py:2395-2399.
    const resolution: AnalyzeResult["barcode_prefix_resolution"] = {
      forward: {
        axis: "F",
        tail: "GGTCTC",
        tail_length: 6,
        barcode_count: 12,
        seed_lengths: [11, 11, 10],
      },
      reverse: {
        axis: "R",
        tail: "CGTCTC",
        tail_length: 6,
        barcode_count: 8,
        seed_lengths: [11, 11],
      },
      note: "Barcode seeds were cut at the sequence every primer on an axis shares...",
    };
    expect(resolution?.forward.tail_length).toBe(6);
    expect(resolution?.reverse.seed_lengths).toHaveLength(2);
  });
});

describe("export results keep the provenance artifacts the sidecar writes", () => {
  it("carries manifest_path and checksum_path on all three export shapes", () => {
    // python-core/sidecar_kuro/handlers/export.py:318-323, :375-380, :473-478.
    // write_run_manifest and write_output_checksum both return a Path that the
    // handler stringifies, so a live sidecar always sends a string.
    const excel: ExportResult = {
      success: true,
      filepath: "/tmp/out.xlsx",
      manifest_path: "/tmp/out.xlsx.manifest.json",
      checksum_path: "/tmp/out.xlsx.sha256",
    };
    const order: ExportOrderResult = {
      success: true,
      filepath: "/tmp/order.csv",
      format: "idt",
      primer_count: 96,
      manifest_path: "/tmp/order.csv.manifest.json",
      checksum_path: "/tmp/order.csv.sha256",
    };
    const mapping: ExportMappingResult = {
      success: true,
      filepath: "/tmp/map.csv",
      format: "echo",
      primer_count: 96,
      manifest_path: "/tmp/map.csv.manifest.json",
      checksum_path: "/tmp/map.csv.sha256",
    };

    for (const result of [excel, order, mapping]) {
      expect(result.manifest_path).toContain("manifest.json");
      expect(result.checksum_path).toContain("sha256");
    }
  });
});

describe("CombinatorialDemuxStats carries the drop-reason breakdown", () => {
  it("accepts the 15 keys _demux_one_nb emits per native barcode", () => {
    // combinatorial_demux.py:3199-3204 spreads _DEMUX_NB_STAT_KEYS (8) plus
    // _DEMUX_NB_DROP_KEYS (7, named at :367-375).
    const stats: CombinatorialDemuxStats = {
      total_reads: 1000,
      passed_mapq: 950,
      passed_coverage: 900,
      assigned_reads: 820,
      ambiguous_dropped: 80,
      chimera_splits: 4,
      wells_with_reads: 90,
      wells_with_min_reads: 84,
      drop_short_window_read_5p: 10,
      drop_short_window_read_3p: 8,
      drop_no_barcode_f: 20,
      drop_no_barcode_r: 18,
      drop_ambiguous_tie_f: 12,
      drop_ambiguous_tie_r: 9,
      drop_both_axes: 3,
    };

    const dropSum =
      (stats.drop_short_window_read_5p ?? 0) +
      (stats.drop_short_window_read_3p ?? 0) +
      (stats.drop_no_barcode_f ?? 0) +
      (stats.drop_no_barcode_r ?? 0) +
      (stats.drop_ambiguous_tie_f ?? 0) +
      (stats.drop_ambiguous_tie_r ?? 0) +
      (stats.drop_both_axes ?? 0);
    expect(dropSum).toBe(stats.ambiguous_dropped);
  });

  it("accepts a resume that omits all seven", () => {
    // A marker written before the breakdown existed omits them, and
    // combinatorial_demux.py:3113-3122 says the omission must survive: absent
    // means "could not measure", which is not the same claim as 0.
    const resumed: CombinatorialDemuxStats = {
      total_reads: 1000,
      passed_mapq: 950,
      passed_coverage: 900,
      assigned_reads: 820,
      ambiguous_dropped: 80,
      chimera_splits: 4,
      wells_with_reads: 90,
      wells_with_min_reads: 84,
    };
    expect(resumed.drop_both_axes).toBeUndefined();
    expect(resumed.ambiguous_dropped).toBe(80);
  });
});

describe("EvolveproLoadResult keeps the top-level start-codon counters", () => {
  it("accepts the pair load_evolvepro_csv returns at the top level", () => {
    // kuma_core/kuro/evolvepro.py:715-716, passed through unfiltered by
    // python-core/sidecar_kuro/handlers/misc.py:236-237. Built at
    // evolvepro.py:583-585, so never null: the count is a len() and the list a
    // comprehension.
    const result: EvolveproLoadResult = {
      variants: ["D12N"],
      y_preds: [0.8],
      total_count: 1,
      selected_count: 1,
      start_codon_removed: 2,
      start_codon_removed_variants: ["M1A", "M1V"],
    };
    expect(result.start_codon_removed).toBe(result.start_codon_removed_variants?.length);
  });
});
