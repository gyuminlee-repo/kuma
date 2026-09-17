import type { RunQuality } from "@/types/mame/run_quality";

export const runQualityFixture = {
  severity: null, median_well_reads: 500, min_read_count: 100, depth_ok: true,
  wells_under_floor: 0, wells_total: 96, recommended_reads: 1000,
  flow_cell_id: null, pore_start: null, pore_end: null, pore_warranty_min: 800,
  reused_from: null, thresholds: {}, findings: [],
  position_recurrence: {
    lower_bound: true, wells_contributing: 5, wells_truncated: 1,
    positions_seen: 2, positions_single_well: 1,
    positions: [{ position: 512, wells: 3, median_weak_strand_share: null,
      min_weak_strand_share: null, max_weak_strand_share: null, shares_known: 0, shares_unknown: 3 }],
  },
  indel_recurrence: {
    lower_bound: true, lower_bound_cause: "omission", wells_scored: 96,
    deletion_wells_contributing: 3, deletion_wells_omitted: 1,
    deletion_positions_seen: 1, deletion_positions_single_well: 0,
    insertion_wells_contributing: 2, insertion_wells_unreported: 0,
    insertion_anchors_tied: 0, insertion_anchors_seen: 1, insertion_anchors_single_well: 0,
    deletions: [{ position: 669, wells: 3, expected_variants: 1 }],
    insertions: [{ anchor: 900, wells: 2, expected_variants: 2, distinct_sequences: 1 }],
  },
  read_length: {
    reference_length_bp: 1715, near_reference_tolerance: 0.2, concatemer_multiple: 2,
    histograms: [{ read_length_type: "EstimatedBases", bucket_value_type: "ReadLengths", n50: 3257,
      plot: { bucket_starts: [0], bucket_ends: [4000], bucket_values: [8000], total: 8000 }, outliers: null,
      n50_over_reference: 1.9, near_reference_bases_fraction: 0.21, over_2x_reference_bases_fraction: 0.4 }],
    qscore_histograms: [{ bucket_value_type: null, bucket_starts: [10], bucket_ends: [20],
      series: [{ filtering: [{ read_type: "simplex" }], modal_q_score: null, bucket_values: [100] }] }],
    provenance: { n50: { source: "MinKNOW", kind: "instrument_report", computed: false, enforced: false } },
  },
} satisfies RunQuality;
