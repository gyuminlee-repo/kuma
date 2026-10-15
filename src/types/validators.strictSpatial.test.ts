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
  it("accepts tie-averaged ranks without substituting arbitrary integer ranks", () => {
    const report = syntheticFullDfTestFixture(12);
    const comparison = { ...report.comparison, selected: { ...report.comparison?.selected, score_mean: 1, mean_score_rank: 57.5 },
      top_n: { ...report.comparison?.top_n, score_mean: 1, mean_score_rank: 57.5 }, score_gap_to_top_n: 0 };
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
    { score_available: false }, { selected: null }, { top_n: null }, { top_n_variants: ["A999C"] },
    { top_n_overlap_count: 13 }, { top_n_overlap_count: 1.5 }, { score_gap_to_top_n: -1 },
    { score_gap_to_top_n: Number.POSITIVE_INFINITY }, { score_gap_to_top_n: 0 },
  ])("rejects malformed or contradictory diagnostics: %j", (patch) => {
    const report = syntheticFullDfTestFixture(12);
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison: { ...report.comparison, ...patch } } })).toBe(false);
  });
  it.each([
    { variant_count: 11 }, { site_count: 5 }, { max_variants_per_site: 3 },
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
    const comparison = { ...report.comparison, selected: { ...report.comparison?.selected, score_mean: null }, score_gap_to_top_n: null };
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(true);
  });
  it("accepts an unavailable gap when finite raw means have an overflowing difference", () => {
    const report = syntheticFullDfTestFixture(12);
    const comparison = { ...report.comparison, selected: { ...report.comparison?.selected, score_mean: -1e308 },
      top_n: { ...report.comparison?.top_n, score_mean: 1e308 }, score_gap_to_top_n: null };
    expect(valid({ ...response(report), strict_spatial: { ...report, comparison } })).toBe(true);
  });
});
