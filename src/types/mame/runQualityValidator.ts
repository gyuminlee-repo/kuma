import { isRecord } from "../validators";

type Guard = (value: unknown) => boolean;
const number: Guard = (v) => typeof v === "number" && Number.isFinite(v);
const string: Guard = (v) => typeof v === "string";
const boolean: Guard = (v) => typeof v === "boolean";
const nullable = (guard: Guard): Guard => (v) => v === null || guard(v);
const optional = (guard: Guard): Guard => (v) => v === undefined || guard(v);
const array = (guard: Guard): Guard => (v) => Array.isArray(v) && v.every(guard);
const record = (guard: Guard): Guard => (v) => isRecord(v) && Object.values(v).every(guard);
const fields = (shape: Readonly<Record<string, Guard>>): Guard => (v) =>
  isRecord(v) && Object.entries(shape).every(([key, guard]) => guard(v[key]));
const oneOf = (...values: readonly string[]): Guard => (v) =>
  typeof v === "string" && values.includes(v);
const nullableNumber = nullable(number);
const optionalNumber = optional(number);
const numbers = array(number);

const positionRecurrence = fields({
  lower_bound: boolean,
  wells_contributing: number,
  wells_truncated: number,
  positions_seen: number,
  positions_single_well: number,
  strand_information: optional(oneOf("absent", "present", "no_data")),
  positions: array(fields({
    position: number, wells: number,
    recurrence_rate: optionalNumber,
    median_minor_fraction: optionalNumber,
    min_minor_fraction: optionalNumber,
    max_minor_fraction: optionalNumber,
    median_weak_strand_share: nullableNumber,
    min_weak_strand_share: nullableNumber,
    max_weak_strand_share: nullableNumber,
    shares_known: number, shares_unknown: number,
  })),
});

const indelRecurrence = fields({
  lower_bound: boolean, lower_bound_cause: string,
  wells_scored: number,
  deletion_wells_contributing: number,
  deletion_wells_omitted: number,
  deletion_positions_seen: number,
  deletion_positions_single_well: number,
  insertion_wells_contributing: number,
  insertion_wells_unreported: number,
  insertion_anchors_tied: number,
  insertion_anchors_seen: number,
  insertion_anchors_single_well: number,
  deletions: array(fields({ position: number, wells: number, expected_variants: number })),
  insertions: array(fields({ anchor: number, wells: number, expected_variants: number, distinct_sequences: number })),
});

const buckets = fields({ bucket_starts: numbers, bucket_ends: numbers, bucket_values: numbers, total: number });
const readLength = fields({
  reference_length_bp: nullableNumber,
  near_reference_tolerance: number,
  concatemer_multiple: number,
  histograms: nullable(array(fields({
    read_length_type: nullable(string), bucket_value_type: nullable(string),
    n50: nullableNumber, plot: nullable(buckets), outliers: nullable(buckets),
    n50_over_reference: nullableNumber,
    near_reference_bases_fraction: nullableNumber,
    over_2x_reference_bases_fraction: nullableNumber,
  }))),
  qscore_histograms: nullable(array(fields({
    bucket_value_type: nullable(string), bucket_starts: numbers, bucket_ends: numbers,
    series: array(fields({
      filtering: array(record(string)), modal_q_score: nullableNumber, bucket_values: numbers,
    })),
  }))),
  provenance: record(fields({
    source: string, kind: oneOf("instrument_report", "derived"), computed: boolean, enforced: boolean,
  })),
});

const severity = oneOf("blocking", "warning");
const runQuality = fields({
  severity: nullable(severity), median_well_reads: nullableNumber,
  min_read_count: nullableNumber, depth_ok: nullable(boolean),
  wells_under_floor: number, wells_total: number, recommended_reads: number,
  flow_cell_id: nullable(string), pore_start: nullableNumber, pore_end: nullableNumber,
  pore_warranty_min: number,
  reused_from: nullable(fields({
    flow_cell_id: optional(nullable(string)), product_code: optional(nullable(string)),
    run_dir: optional(nullable(string)), started: optional(nullable(string)),
    pore_start: optional(nullableNumber), pore_end: optional(nullableNumber),
  })),
  edge_variants: optional(array(string)), edge_margin_bp: optionalNumber,
  amplicon_extracted: optional(nullable(boolean)), amplicon_skip_reason: optional(nullable(string)),
  thresholds: record(fields({
    // serialise_run_quality copies min_read_count, which can legitimately be null.
    value: optional(nullableNumber), coverage: optionalNumber, minor_allele_fraction: optionalNumber,
    source: string, kind: oneOf("vendor_default", "vendor_recommendation", "literature", "vendor_warranty", "self_set"),
    provisional: optional(boolean), enforced: optional(boolean),
  })),
  // Findings are extensible scientific metadata; unknown codes are displayed by i18n.
  findings: array(fields({ code: string, severity })),
  position_recurrence: optional(positionRecurrence),
  indel_recurrence: optional(indelRecurrence),
  read_length: optional(readLength),
});

/** Shared RPC/file boundary for run_quality only, not the entire analyze contract.
 * Missing legacy blocks stay missing; a present malformed block rejects the result.
 * Unknown metadata is retained verbatim, never coerced or zero-filled. */
export function hasValidRunQuality(value: unknown): boolean {
  return isRecord(value) && optional(runQuality)(value.run_quality);
}
