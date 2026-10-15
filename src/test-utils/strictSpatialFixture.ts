import type { StrictSpatialResult } from "@/types/models";

export function strictSpatialFixture(overrides: Partial<StrictSpatialResult> = {}): StrictSpatialResult {
  return {
    schema_version: 1, source_accession: "P12345", source_sha256: "a".repeat(64),
    reference_sha256: "b".repeat(64), candidate_sha256: "c".repeat(64), score_order: "desc", score_available: true,
    pdb_text: "ATOM      1  CA  ALA A  12       1.000   2.000   3.000  1.00 90.00           C  \nEND\n",
    coordinate_frame: "reference", selection_policy: "single-site-full-pool-fps-v1",
    selected_variants: ["A2G", "A4V"], selected_positions: [2, 4],
    mapping: [
      { reference_position: 2, structure_position: 12, chain_id: "A", insertion_code: "", coordinate: [1, 2, 3] },
      { reference_position: 4, structure_position: 14, chain_id: "A", insertion_code: "", coordinate: [9, 2, 3] },
      { reference_position: 5, structure_position: 15, chain_id: "A", insertion_code: "", coordinate: [3, 2, 3] },
    ], eligible_positions: [2, 4, 5], excluded: [{ variant: "A3G", reason: "missing_or_nonfinite_coordinate" }],
    requested_count: 2, eligible_site_count: 3,
    source_row_count: 6, parsed_variant_count: 5, parsing_omitted_count: 1,
    start_position_omitted_count: 1, duplicate_variant_omitted_count: 0, ...overrides,
  };
}
