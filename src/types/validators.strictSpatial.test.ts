import { describe, expect, it } from "vitest";
import { distinctSpatial95Fixture, strictSpatialFixture, syntheticFullDfTestFixture } from "@/test-utils/strictSpatialFixture";
import { getRpcResultValidator } from "./validators";

describe("strict spatial response contract", () => {
  const result = () => ({ variants: ["A2G", "A4V"], y_preds: [2, 1], selected_count: 2, total_count: 4, strict_spatial: strictSpatialFixture() });
  const valid = getRpcResultValidator("load_evolvepro_csv");
  it("accepts legacy responses and complete certificates", () => {
    expect(valid(result())).toBe(true);
    expect(valid({ ...result(), strict_spatial: undefined })).toBe(true);
  });
  it.each([{}, { schema_version: 2 }, { mapping: [{ reference_position: 2, coordinate: [1, 2, Number.NaN] }] }, { candidate_sha256: null }])("rejects malformed certificates: %j", (patch) => {
    const value = result();
    expect(valid({ ...value, strict_spatial: Object.keys(patch).length ? { ...value.strict_spatial, ...patch } : patch })).toBe(false);
  });
  it("preserves source features with uncertain ranges and raw evidence", () => {
    const features = [{ type: "Binding site", ligand: { name: "Metal" }, evidences: [{ evidenceCode: "ECO:0000269" }], location: { start: { modifier: "UNCERTAIN" } } }];
    const value = { accession: "P12345", source: "uniprot", has_annotation: true, active_site_positions: [], binding_positions: [], features, annotation_status: "present", sequence_version: 2 };
    expect(getRpcResultValidator("fetch_active_site_residues")(value)).toBe(true);
    expect(value.features).toBe(features);
  });
  it("accepts 95 distinct variants at only five sites", () => {
    const report = distinctSpatial95Fixture();
    expect(valid({ variants: report.selected_variants, y_preds: Array<number>(95).fill(1),
      selected_count: 95, total_count: 95, strict_spatial: report })).toBe(true);
  });
  it.each([
    { budget_mode: "unique_sites", selection_policy: "single-site-full-pool-fps-v1" },
    { selected_variant_count: 5 }, { selected_site_count: 95 }, { eligible_site_count: 95 },
    { eligible_variant_count: 94 }, { site_cap: 18 }, { site_cap: 1.5 },
    { selected_variants: Array<string>(95).fill("A2C") },
    { site_multiplicities: [{ reference_position: 2, variant_count: 95 }] },
    { selected_positions: Array<number>(95).fill(2) }, { mapping: [] },
  ])("rejects inconsistent variant/site accounting: %j", (patch) => {
    expect(valid({ ...result(), strict_spatial: { ...distinctSpatial95Fixture(), ...patch } })).toBe(false);
  });
});

describe("strict spatial df_test comparison contract", () => {
  const valid = getRpcResultValidator("load_evolvepro_csv");
  function response(report = syntheticFullDfTestFixture(12)) {
    return { variants: report.selected_variants, y_preds: Array<number>(report.requested_count).fill(1),
      selected_count: report.requested_count, total_count: report.eligible_variant_count, strict_spatial: report };
  }
  it.each([1, 12, 95, 100])("accepts independent variant and site counts at user N=%s", (count) => {
    const value = response(syntheticFullDfTestFixture(count));
    expect(value.total_count).toBeGreaterThan(count);
    expect(valid(value)).toBe(true);
  });
  it.each(["asc", "desc"] as const)("accepts configured %s score order and fractional mean ranks", (order) => {
    const report = syntheticFullDfTestFixture(12, true, order);
    expect(report.comparison?.score_gap_to_top_n).toBe(42.5);
    expect(valid(response(report))).toBe(true);
  });
  // All three baselines coincide in this fixture, so a top_n edit applies to each.
  function withBaselines(report: ReturnType<typeof syntheticFullDfTestFixture>, selected: object, topN: object | null, gap: number | null) {
    const comparison = report.comparison;
    const block = { top_n: topN === null ? comparison?.top_n : { ...comparison?.top_n, ...topN }, score_gap_to_top_n: gap };
    return { ...comparison, selected: { ...comparison?.selected, ...selected }, ...block,
      eligible_top_n: { ...comparison?.eligible_top_n, ...block },
      representative_top_n: { ...comparison?.representative_top_n, ...block } };
  }
  it("accepts tie-averaged ranks without substituting arbitrary integer ranks", () => {
    const report = syntheticFullDfTestFixture(12);
    const comparison = withBaselines(report, { score_mean: 1, mean_score_rank: 57.5 }, { score_mean: 1, mean_score_rank: 57.5 }, 0);
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(true);
  });
  it("accepts geometry-only comparison when scores are missing", () => {
    expect(valid(response(syntheticFullDfTestFixture(12, false)))).toBe(true);
  });
  it("accepts identical full-pool profiles when all candidates are requested", () => {
    const report = syntheticFullDfTestFixture(114);
    expect(report.comparison?.top_n_overlap_count).toBe(114);
    expect(report.comparison?.score_gap_to_top_n).toBe(0);
    expect(report.comparison?.selected).toEqual(report.comparison?.top_n);
    expect(valid(response(report))).toBe(true);
  });
  it.each([null, {}, { selected: {} }])("rejects a present but incomplete comparison: %j", (comparison) => {
    const report = syntheticFullDfTestFixture(12);
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(false);
  });
  it.each([
    { baseline: "random" }, { universe: "full-sequence" }, { candidate_site_count: 7 },
    // The pre-2026-10-12 universe meant per-site representatives; it must not
    // be shown under the new raw-pool label.
    { universe: "eligible-variants-after-budget-and-cap-policy" }, { representative_top_n: undefined },
    // Until 2026-10-13 the primary Top-N was taken from the eligible variants
    // only; a response still labelled that way must not be shown as the input Top-N.
    { universe: "eligible-variants-before-budget-and-cap-policy" },
    { eligible_top_n: undefined }, { eligible_top_n: { universe: "input-variants-before-spatial-eligibility" } },
    { top_n_excluded: undefined }, { top_n_excluded: null }, { top_n_excluded: [{ variant: "A2C" }] },
    { top_n_excluded: [{ variant: "A999C", reason: "low_confidence_coordinate" }] },
    { representative_top_n: { universe: "eligible-variants-before-budget-and-cap-policy" } },
    { score_available: false }, { selected: null }, { top_n: null }, { top_n_variants: ["A999C"] },
    { top_n_overlap_count: 13 }, { top_n_overlap_count: 1.5 }, { score_gap_to_top_n: -1 },
    { score_gap_to_top_n: Number.POSITIVE_INFINITY }, { score_gap_to_top_n: 0 },
  ])("rejects malformed or contradictory diagnostics: %j", (patch) => {
    const report = syntheticFullDfTestFixture(12);
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison: { ...report.comparison, ...patch } } })).toBe(false);
  });
  it.each([
    { variant_count: 11 }, { site_count: 5 }, { max_variants_per_site: 3 },
    { spatial_variant_count: 11 }, { spatial_variant_count: 13 }, { spatial_variant_count: undefined },
    { coverage_mean_distance: null, coverage_max_distance: null },
    { minimum_site_distance: null }, { minimum_site_distance: 0 },
    { coverage_mean_distance: -1 }, { coverage_mean_distance: 1, coverage_max_distance: 0 },
    { coverage_max_distance: Number.NaN }, { score_mean: Number.POSITIVE_INFINITY },
    { mean_score_rank: 0 }, { mean_score_rank: 115 },
  ])("rejects invalid selected profile accounting: %j", (patch) => {
    const report = syntheticFullDfTestFixture(12);
    const comparison = { ...report.comparison, selected: { ...report.comparison?.selected, ...patch } };
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(false);
  });
  it("rejects fake zero scores when no scores are available", () => {
    const report = syntheticFullDfTestFixture(12, false);
    const comparison = { ...report.comparison, selected: { ...report.comparison?.selected, score_mean: 0 } };
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(false);
  });
  it("preserves selection when raw score summaries overflow", () => {
    const report = syntheticFullDfTestFixture(12);
    const comparison = withBaselines(report, { score_mean: null }, null, null);
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(true);
  });
  it("accepts an unavailable gap when finite raw means have an overflowing difference", () => {
    const report = syntheticFullDfTestFixture(12);
    const comparison = withBaselines(report, { score_mean: -1e308 }, { score_mean: 1e308 }, null);
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(true);
  });
});

describe("strict spatial raw-pool Top-N and coordinate confidence", () => {
  const valid = getRpcResultValidator("load_evolvepro_csv");
  const profile = (variants: number, sites: number, perSite: number, mean: number, rank: number, minimum: number | null) => ({
    variant_count: variants, spatial_variant_count: variants, site_count: sites, max_variants_per_site: perSite, minimum_site_distance: minimum,
    coverage_mean_distance: 1, coverage_max_distance: 2, score_mean: mean, mean_score_rank: rank });
  // unique_sites: the raw Top-2 repeats site 2, the representative Top-2 does not.
  function report(overrides: Record<string, unknown> = {}) {
    const rawTop = { top_n: profile(2, 1, 2, 9.5, 1.5, null), top_n_variants: ["A2G", "A2V"], top_n_overlap_count: 1, score_gap_to_top_n: 3.5 };
    return strictSpatialFixture({
      eligible_variant_count: 4,
      comparison: {
        baseline: "configured-score-top-n", universe: "input-variants-before-spatial-eligibility",
        candidate_site_count: 3, score_available: true, selected: profile(2, 2, 1, 6, 2.5, 8),
        // The excluded A3G scores below both, so the input Top-2 is the eligible Top-2.
        ...rawTop, top_n_excluded: [], eligible_top_n: { universe: "eligible-variants-before-budget-and-cap-policy", ...rawTop },
        representative_top_n: { universe: "eligible-variants-after-budget-and-cap-policy",
          top_n: profile(2, 2, 1, 8, 2, 2), top_n_variants: ["A2G", "A5C"], top_n_overlap_count: 1, score_gap_to_top_n: 2 },
      }, ...overrides,
    });
  }
  const response = (strict: ReturnType<typeof strictSpatialFixture>) => ({ variants: strict.selected_variants, y_preds: [2, 1],
    selected_count: 2, total_count: 4, strict_spatial: strict });
  it("accepts a raw-pool Top-N that repeats a site under the one-per-site budget", () => {
    expect(valid(response(report()))).toBe(true);
  });
  it("still applies the one-per-site budget to the representative baseline", () => {
    const strict = report();
    const comparison = { ...strict.comparison, representative_top_n: { ...strict.comparison?.representative_top_n,
      top_n: profile(2, 1, 2, 9.5, 1.5, null), top_n_variants: ["A2G", "A2V"], score_gap_to_top_n: 3.5 } };
    expect(valid(response({ ...strict, comparison } as typeof strict))).toBe(false);
  });
  it("rejects an eligible Top-N that differs from an input Top-N with no excluded member", () => {
    const strict = report();
    const comparison = { ...strict.comparison, eligible_top_n: { ...strict.comparison?.representative_top_n,
      universe: "eligible-variants-before-budget-and-cap-policy" } };
    expect(valid(response({ ...strict, comparison } as typeof strict))).toBe(false);
  });
  const lowConfidence = { variant: "A3G", reason: "low_confidence_coordinate" };
  // pLDDT mapping consistent with one low-confidence residue (position 3).
  function plddtReport(overrides: Record<string, unknown> = {}) {
    const strict = report();
    const mapping = [...strict.mapping.map((row) => ({ ...row, confidence: 90 })),
      { reference_position: 3, structure_position: 13, chain_id: "A", insertion_code: "", coordinate: [5, 2, 3] as [number, number, number], confidence: 30 }];
    return report({ mapping, excluded: [lowConfidence], confidence_source: "alphafold_plddt",
      coordinate_confidence: { source: "alphafold_plddt", threshold: 50, low_confidence_residue_count: 1, excluded_variant_count: 1 },
      ...overrides } as never);
  }
  it("accepts a pLDDT report whose residue count matches the mapping", () => {
    expect(valid(response(plddtReport()))).toBe(true);
  });
  it("rejects a pLDDT report whose mapping or top-level source disagrees", () => {
    const strict = plddtReport();
    const confidence = strict.coordinate_confidence;
    expect(valid(response({ ...strict, coordinate_confidence: { ...confidence!, low_confidence_residue_count: 2 } }))).toBe(false);
    expect(valid(response({ ...strict, mapping: strict.mapping.map((row, index) => (index === 0 ? { ...row, confidence: null } : row)) }))).toBe(false);
    expect(valid(response({ ...strict, mapping: strict.mapping.map(({ confidence: _drop, ...row }) => row) }))).toBe(false);
    expect(valid(response({ ...strict, confidence_source: "unavailable" }))).toBe(false);
    expect(valid(response({ ...strict, confidence_source: "b_factor" } as never))).toBe(false);
  });
  // The certificate's own pLDDT decides which residues may be picked. `comparison`
  // is dropped (legacy shape) so only the confidence cross-checks can reject it.
  function plddtSelection(patch: Record<string, unknown> = {}): unknown {
    const base = plddtReport({ comparison: undefined });
    return { ...response(base), strict_spatial: { ...base, ...patch } };
  }
  const selectsSiteThree = {
    selected_variants: ["A3G", "A4V"], selected_positions: [3, 4],
    site_multiplicities: [{ reference_position: 3, variant_count: 1 }, { reference_position: 4, variant_count: 1 }],
  };
  const siteThreeAt = (confidence: number | null) => plddtReport().mapping.map((row) => (
    row.reference_position === 3 ? { ...row, confidence } : row));
  it("accepts the consistent pLDDT report once the comparison block is dropped", () => {
    expect(valid(plddtSelection())).toBe(true);
  });
  it("rejects a selection that includes a residue below the pLDDT threshold", () => {
    // Residue 3 has pLDDT 30, is eligible, selected and also listed as excluded.
    expect(valid(plddtSelection({ ...selectsSiteThree, eligible_positions: [2, 3, 4] }))).toBe(false);
  });
  it("rejects eligible positions that include a residue below the pLDDT threshold", () => {
    expect(valid(plddtSelection({ eligible_positions: [2, 3, 4, 5], eligible_site_count: 4 }))).toBe(false);
  });
  it("rejects a selected variant that is also excluded as low confidence", () => {
    const patch = { ...selectsSiteThree, eligible_positions: [2, 3, 4], mapping: siteThreeAt(90),
      coordinate_confidence: { source: "alphafold_plddt", threshold: 50, low_confidence_residue_count: 0, excluded_variant_count: 1 } };
    expect(valid(plddtSelection(patch))).toBe(false);
    // The same mapping without the contradictory exclusion is a plain, valid selection.
    expect(valid(plddtSelection({ ...patch, excluded: [],
      coordinate_confidence: { ...patch.coordinate_confidence, excluded_variant_count: 0 } }))).toBe(true);
  });
  it("treats a residue at exactly the threshold as eligible, as the sidecar does", () => {
    const patch = { ...selectsSiteThree, eligible_positions: [2, 3, 4], mapping: siteThreeAt(50), excluded: [],
      coordinate_confidence: { source: "alphafold_plddt", threshold: 50, low_confidence_residue_count: 0, excluded_variant_count: 0 } };
    expect(valid(plddtSelection(patch))).toBe(true);
  });
  it("keeps an unavailable-confidence report free of pLDDT selection checks", () => {
    const patch = { ...selectsSiteThree, eligible_positions: [2, 3, 4], mapping: siteThreeAt(null).map((row) => ({ ...row, confidence: null })),
      excluded: [], confidence_source: "unavailable",
      coordinate_confidence: { source: "unavailable", threshold: null, low_confidence_residue_count: 0, excluded_variant_count: 0 } };
    expect(valid(plddtSelection(patch))).toBe(true);
  });
  it.each([
    [{ source: "alphafold_plddt", threshold: 50, low_confidence_residue_count: 1, excluded_variant_count: 1 }, [lowConfidence], true],
    [{ source: "unavailable", threshold: null, low_confidence_residue_count: 0, excluded_variant_count: 0 }, [], true],
    [{ source: "alphafold_plddt", threshold: 70, low_confidence_residue_count: 1, excluded_variant_count: 1 }, [lowConfidence], false],
    [{ source: "unavailable", threshold: 50, low_confidence_residue_count: 0, excluded_variant_count: 0 }, [], false],
    [{ source: "unavailable", threshold: null, low_confidence_residue_count: 0, excluded_variant_count: 0 }, [lowConfidence], false],
    [{ source: "alphafold_plddt", threshold: 50, low_confidence_residue_count: 1, excluded_variant_count: 2 }, [lowConfidence], false],
    [{ source: "b_factor", threshold: null, low_confidence_residue_count: 0, excluded_variant_count: 0 }, [], false],
  ])("checks the confidence report %j against the exclusions", (confidence, excluded, expected) => {
    expect(valid(response(plddtReport({ coordinate_confidence: confidence, excluded, confidence_source: undefined })))).toBe(expected);
  });
  it("rejects an out-of-range per-residue pLDDT", () => {
    const strict = report();
    const mapping = strict.mapping.map((row, index) => (index === 0 ? { ...row, confidence: 120 } : row));
    expect(valid(response({ ...strict, mapping }))).toBe(false);
    expect(valid(response({ ...strict, mapping: strict.mapping.map((row) => ({ ...row, confidence: 91.5 })) }))).toBe(true);
  });
});

describe("strict spatial input Top-N with members excluded from spatial selection", () => {
  const valid = getRpcResultValidator("load_evolvepro_csv");
  const missing = "missing_or_nonfinite_coordinate";
  type Metrics = { spatial?: number; sites: number; perSite: number; minimum: number | null; coverage?: [number, number] | null };
  const profile = (mean: number, rank: number, { spatial = 2, sites, perSite, minimum, coverage = [1, 2] }: Metrics) => ({
    variant_count: 2, spatial_variant_count: spatial, site_count: sites, max_variants_per_site: perSite,
    minimum_site_distance: minimum, coverage_mean_distance: coverage?.[0] ?? null, coverage_max_distance: coverage?.[1] ?? null,
    score_mean: mean, mean_score_rank: rank });
  // Scores: A3G 10 (no coordinate), A2G 9, A5C 8, A4V 3. Picks are A2G and A4V.
  const eligibleTop = { top_n: profile(8.5, 2.5, { sites: 2, perSite: 1, minimum: 2 }),
    top_n_variants: ["A2G", "A5C"], top_n_overlap_count: 1, score_gap_to_top_n: 2.5 };
  function report(patch: Record<string, unknown> = {}, overrides: Record<string, unknown> = {}) {
    return strictSpatialFixture({
      comparison: {
        baseline: "configured-score-top-n", universe: "input-variants-before-spatial-eligibility",
        candidate_site_count: 3, score_available: true, selected: profile(6, 3, { sites: 2, perSite: 1, minimum: 8 }),
        top_n: profile(9.5, 1.5, { spatial: 1, sites: 1, perSite: 1, minimum: null }),
        top_n_variants: ["A3G", "A2G"], top_n_overlap_count: 1, score_gap_to_top_n: 3.5,
        top_n_excluded: [{ variant: "A3G", reason: missing }],
        eligible_top_n: { universe: "eligible-variants-before-budget-and-cap-policy", ...eligibleTop },
        representative_top_n: { universe: "eligible-variants-after-budget-and-cap-policy", ...eligibleTop },
        ...patch,
      } as never, ...overrides,
    });
  }
  const response = (strict: ReturnType<typeof strictSpatialFixture>) => ({ variants: strict.selected_variants, y_preds: [9, 3],
    selected_count: 2, total_count: 4, strict_spatial: strict });
  const topN = (patch: Record<string, unknown>) => ({ ...report().comparison?.top_n, ...patch });

  it("accepts a Top-N that names an excluded variant and lists it with the same reason", () => {
    expect(valid(response(report()))).toBe(true);
  });
  it.each([
    ["the pre-change universe label", { universe: "eligible-variants-before-budget-and-cap-policy" }],
    ["an excluded member left out of the list", { top_n_excluded: [] }],
    ["a listed variant that is not in the Top-N", { top_n_excluded: [{ variant: "A7G", reason: missing }] }],
    ["an extra listed variant that is in the Top-N but not excluded",
      { top_n_excluded: [{ variant: "A3G", reason: missing }, { variant: "A2G", reason: missing }] }],
    ["a reason that differs from the response's own exclusion", { top_n_excluded: [{ variant: "A3G", reason: "explicit_exclusion" }] }],
    ["distance members counted beyond the usable ones", { top_n: topN({ spatial_variant_count: 2 }) }],
    ["more sites than usable members", { top_n: topN({ site_count: 2, minimum_site_distance: 4 }) }],
    ["an excluded variant inside the eligible Top-N", { eligible_top_n: { ...report().comparison?.eligible_top_n,
      top_n_variants: ["A3G", "A2G"], top_n: topN({}), score_gap_to_top_n: 3.5 } }],
    ["a selected rank beyond the ranked input", { selected: { ...report().comparison?.selected, mean_score_rank: 4.5 } }],
  ])("rejects %s", (_label, patch) => {
    expect(valid(response(report(patch)))).toBe(false);
  });
  it("rejects a Top-N member whose exclusion leaves it unrankable", () => {
    const unranked = [{ variant: "A3G", reason: "nonfinite_score" }];
    expect(valid(response(report({ top_n_excluded: unranked }, { excluded: unranked })))).toBe(false);
  });

  // Both best scores lack a coordinate: nothing in the Top-N can be placed.
  const second = { variant: "A6G", reason: "explicit_exclusion" };
  const unplaced = (top: Record<string, unknown> = {}) => report({
    selected: profile(6, 4, { sites: 2, perSite: 1, minimum: 8 }),
    top_n: { ...profile(10.5, 1.5, { spatial: 0, sites: 0, perSite: 0, minimum: null, coverage: null }), ...top },
    top_n_variants: ["A6G", "A3G"], top_n_overlap_count: 0, score_gap_to_top_n: 4.5,
    top_n_excluded: [second, { variant: "A3G", reason: missing }],
    eligible_top_n: { universe: "eligible-variants-before-budget-and-cap-policy", ...eligibleTop,
      top_n: { ...eligibleTop.top_n, mean_score_rank: 3.5 } },
    representative_top_n: { universe: "eligible-variants-after-budget-and-cap-policy", ...eligibleTop,
      top_n: { ...eligibleTop.top_n, mean_score_rank: 3.5 } },
  }, { excluded: [{ variant: "A3G", reason: missing }, second] });
  it("accepts a Top-N with no usable coordinate when its distances are null", () => {
    // The selected mean rank 4 exceeds the 3 eligible variants: ranks count the excluded input too.
    expect(valid(response(unplaced()))).toBe(true);
  });
  it.each([
    { coverage_mean_distance: 0, coverage_max_distance: 0 }, { minimum_site_distance: 0 },
    { site_count: 1 }, { max_variants_per_site: 1 },
  ])("rejects zero or invented site metrics for a Top-N with no usable coordinate: %j", (top) => {
    expect(valid(response(unplaced(top)))).toBe(false);
  });
});
