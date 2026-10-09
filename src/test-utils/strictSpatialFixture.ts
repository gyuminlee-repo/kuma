import type { StrictSpatialResult } from "@/types/models";

export function strictSpatialFixture(overrides: Partial<StrictSpatialResult> = {}): StrictSpatialResult {
  return {
    schema_version: 1, source_accession: "P12345", source_sha256: "a".repeat(64),
    reference_sha256: "b".repeat(64), candidate_sha256: "c".repeat(64), score_order: "desc", score_available: true,
    pdb_text: "ATOM      1  CA  ALA A  12       1.000   2.000   3.000  1.00 90.00           C  \nEND\n",
    coordinate_frame: "reference", selection_policy: "single-site-full-pool-fps-v1",
    budget_mode: "unique_sites", site_cap: null,
    selected_variants: ["A2G", "A4V"], selected_positions: [2, 4],
    selected_variant_count: 2, selected_site_count: 2, eligible_variant_count: 3,
    site_multiplicities: [{ reference_position: 2, variant_count: 1 }, { reference_position: 4, variant_count: 1 }],
    geometry_variant_min_pair_distance: 8, geometry_site_min_pair_distance: 8,
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

/** All 19 non-alanine substitutions at five sites: N is variants, not sites. */
export function distinctSpatial95Fixture(overrides: Partial<StrictSpatialResult> = {}): StrictSpatialResult {
  const positions = [2, 3, 4, 5, 6];
  const selected = positions.flatMap((position) => [..."CDEFGHIKLMNPQRSTVWY"].map((aa) => `A${position}${aa}`));
  return strictSpatialFixture({
    budget_mode: "distinct_variants", selection_policy: "distinct-variant-full-pool-fps-v1",
    selected_variants: selected, selected_positions: positions.flatMap((position) => Array<number>(19).fill(position)),
    selected_variant_count: 95, selected_site_count: 5, requested_count: 95,
    eligible_variant_count: 95, eligible_site_count: 5, eligible_positions: positions,
    mapping: positions.map((position) => ({ reference_position: position, structure_position: position + 10,
      chain_id: "A", insertion_code: "", coordinate: [position * 4, 2, 3] })),
    site_multiplicities: positions.map((position) => ({ reference_position: position, variant_count: 19 })),
    geometry_variant_min_pair_distance: 0, geometry_site_min_pair_distance: 4,
    source_row_count: 95, parsed_variant_count: 95, parsing_omitted_count: 0,
    start_position_omitted_count: 0, duplicate_variant_omitted_count: 0, excluded: [], ...overrides,
  });
}
