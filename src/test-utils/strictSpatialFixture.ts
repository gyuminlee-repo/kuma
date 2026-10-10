import type { StrictSpatialProfile, StrictSpatialResult } from "@/types/models";

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

/** Synthetic full df_test prediction pool, not the user's private scientific data. */
export function syntheticFullDfTestFixture(
  requestedCount: number, scoresAvailable = true, scoreOrder: "asc" | "desc" = "desc",
): StrictSpatialResult {
  const positions = [2, 3, 4, 5, 6, 7];
  const substitutions = [..."CDEFGHIKLMNPQRSTVWY"];
  const pool = positions.flatMap((position) => substitutions.map((aa) => `A${position}${aa}`));
  if (requestedCount < 1 || requestedCount > pool.length) throw new Error("Synthetic fixture budget is outside its candidate pool");
  const positionOf = (variant: string) => Number(variant.slice(1, -1));
  // Round-robin sites model a spatially spread selection; score Top-N clusters.
  const selected = substitutions.flatMap((aa) => positions.map((position) => `A${position}${aa}`)).slice(0, requestedCount);
  const baseline = pool.slice(0, requestedCount);
  const multiplicities = (variants: string[]) => positions.map((position) => ({ reference_position: position,
    variant_count: variants.filter((variant) => positionOf(variant) === position).length })).filter((row) => row.variant_count > 0);
  const profile = (variants: string[]): StrictSpatialProfile => {
    const sites = [...new Set(variants.map(positionOf))];
    const nearestDistances = positions.map((position) => Math.min(...sites.map((site) => Math.abs(position - site) * 4)));
    const pairDistances = sites.flatMap((position, index) => sites.slice(index + 1).map((site) => Math.abs(position - site) * 4));
    return { variant_count: variants.length, site_count: sites.length,
      max_variants_per_site: Math.max(...multiplicities(variants).map((row) => row.variant_count)),
      minimum_site_distance: pairDistances.length ? Math.min(...pairDistances) : null,
      coverage_mean_distance: nearestDistances.reduce((sum, distance) => sum + distance, 0) / positions.length,
      coverage_max_distance: Math.max(...nearestDistances),
      score_mean: scoresAvailable ? variants.reduce((sum, variant) => sum + (scoreOrder === "asc" ? pool.indexOf(variant) + 1 : pool.length - pool.indexOf(variant)), 0) / variants.length : null,
      mean_score_rank: scoresAvailable ? variants.reduce((sum, variant) => sum + pool.indexOf(variant) + 1, 0) / variants.length : null };
  };
  const selectedProfile = profile(selected);
  const topNProfile = scoresAvailable ? profile(baseline) : null;
  const gap = selectedProfile.score_mean === null || topNProfile?.score_mean == null ? null
    : scoreOrder === "asc" ? selectedProfile.score_mean - topNProfile.score_mean : topNProfile.score_mean - selectedProfile.score_mean;
  return strictSpatialFixture({
    budget_mode: "distinct_variants", selection_policy: "distinct-variant-full-pool-fps-v1",
    score_available: scoresAvailable, score_order: scoreOrder,
    selected_variants: selected, selected_positions: selected.map(positionOf),
    selected_variant_count: requestedCount, selected_site_count: selectedProfile.site_count, requested_count: requestedCount,
    eligible_variant_count: pool.length, eligible_site_count: positions.length, eligible_positions: positions,
    mapping: positions.map((position) => ({ reference_position: position, structure_position: position + 10,
      chain_id: "A", insertion_code: "", coordinate: [position * 4, 2, 3] })),
    site_multiplicities: multiplicities(selected), geometry_site_min_pair_distance: selectedProfile.minimum_site_distance,
    geometry_variant_min_pair_distance: requestedCount < 2 ? null : selectedProfile.max_variants_per_site > 1 ? 0 : selectedProfile.minimum_site_distance,
    source_row_count: pool.length, parsed_variant_count: pool.length, parsing_omitted_count: 0,
    start_position_omitted_count: 0, duplicate_variant_omitted_count: 0, excluded: [],
    comparison: { baseline: "configured-score-top-n", universe: "eligible-variants-after-budget-and-cap-policy",
      candidate_site_count: positions.length, score_available: scoresAvailable, selected: selectedProfile,
      top_n: topNProfile, top_n_variants: scoresAvailable ? baseline : null,
      top_n_overlap_count: scoresAvailable ? baseline.filter((variant) => selected.includes(variant)).length : null,
      score_gap_to_top_n: gap },
  });
}
