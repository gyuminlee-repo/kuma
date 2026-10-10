import { describe, it, expect } from "vitest";
import {
  buildEvolveproLoadParams,
  buildEvolveproLoadStateUpdate,
  collectAnchorVariants,
  resolveSelectionDomains,
  type EvolveproLoadConfig,
} from "./inputSlice.helpers";
import type { Round } from "@/types/round";
import type { MergedRow } from "@/types/mame/activity";
import type { EvolveproLoadResult } from "@/types/models";

// ─── fixtures ─────────────────────────────────────────────────────────────────

function makeRow(mutation: string | null): MergedRow {
  return {
    plate_id: "P01",
    well_id: "A01",
    mutation,
    mutation_source: "kuro_design",
    expected_mutation: mutation,
    called_mutation: mutation,
    ngs_success: true,
    activity_raw_mean: 2.45,
    activity_raw_sd: 0.12,
    activity_replicates: [2.4, 2.5, 2.45],
    replicate_n: 3,
    fold_change: 1.99,
    log2_fc: 0.99,
  };
}

function makeRound(merged_table: MergedRow[], id = "round_1", n = 1): Round {
  return {
    id,
    n,
    created_at: "2026-05-04T00:00:00.000Z",
    status: "activity_linked",
    error_info: null,
    plate_meta: { plates: [] },
    design: {},
    genotype: {},
    activity: null,
    merged_table,
  };
}

function makeConfig(overrides: Partial<EvolveproLoadConfig> = {}): EvolveproLoadConfig {
  return {
    filepath: "/tmp/df_test.csv",
    topN: 10,
    usePipeline: true,
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
    evolveproScoreOrder: "desc",
    evolveproSheetName: null,
    positionDiversityEnabled: false,
    maxPerPosition: 1,
    activeDomains: [],
    excludedDomains: [],
    domainDiversityEnabled: false,
    domainStrategy: "proportional",
    domainOverlapPolicy: "first",
    linkerHandling: "include",
    domainQuotaMin: 0,
    paretoDiversityEnabled: false,
    entropyWeightEnabled: false,
    entropyWeight: 0,
    paretoPoolMultiplier: 1,
    distanceMode: "auto",
    structureAccession: "",
    evolveproRound: 0,
    roundSize: 0,
    refSeq: "",
    structuralDiversityEnabled: false,
    structuralKappa: 0,
    anchorVariants: [],
    ...overrides,
  };
}

// ─── collectAnchorVariants ──────────────────────────────────────────────────

describe("collectAnchorVariants", () => {
  it("returns empty for no rounds", () => {
    expect(collectAnchorVariants([])).toEqual([]);
  });

  it("collects mutations across rounds, deduped, first-seen order", () => {
    const r1 = makeRound([makeRow("F89W"), makeRow("G56D")], "round_1", 1);
    const r2 = makeRound([makeRow("G56D"), makeRow("A24V")], "round_2", 2);
    expect(collectAnchorVariants([r1, r2])).toEqual(["F89W", "G56D", "A24V"]);
  });

  it("drops null and WT entries", () => {
    const r = makeRound([makeRow("F89W"), makeRow(null), makeRow("WT"), makeRow("A24V")]);
    expect(collectAnchorVariants([r])).toEqual(["F89W", "A24V"]);
  });

  it("keeps combo variant strings intact", () => {
    const r = makeRound([makeRow("F89W:G56D"), makeRow("F89W:G56D")]);
    expect(collectAnchorVariants([r])).toEqual(["F89W:G56D"]);
  });
});

// ─── buildEvolveproLoadParams: anchor wiring ────────────────────────────────

describe("buildEvolveproLoadParams anchor_variants", () => {
  it("passes anchorVariants through when usePipeline", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({ anchorVariants: ["F89W", "A24V"] }),
    );
    expect(params.anchor_variants).toEqual(["F89W", "A24V"]);
  });

  it("omits anchor_variants in topN (non-pipeline) mode", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({ usePipeline: false, anchorVariants: ["F89W"] }),
    );
    expect(params).not.toHaveProperty("anchor_variants");
  });

  it("emits structural params with anchors when structural diversity enabled", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({
        structuralDiversityEnabled: true,
        structuralKappa: 0.3,
        anchorVariants: ["F89W"],
      }),
    );
    expect(params.structural_diversity).toBe(true);
    expect(params.structural_kappa).toBe(0.3);
    expect(params.anchor_variants).toEqual(["F89W"]);
  });
});

describe("buildEvolveproLoadParams structure_accession", () => {
  it("sends structure_accession for structural diversity (no pareto) so 3D Cα coords are used", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({
        structuralDiversityEnabled: true,
        paretoDiversityEnabled: false,
        structureAccession: "P01116",
      }),
    );
    expect(params.structure_accession).toBe("P01116");
  });

  it("still sends structure_accession for pareto diversity", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({ paretoDiversityEnabled: true, structureAccession: "P62993" }),
    );
    expect(params.structure_accession).toBe("P62993");
  });

  it("omits structure_accession when neither structural nor pareto is enabled", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({ structureAccession: "P01116" }),
    );
    expect(params).not.toHaveProperty("structure_accession");
  });

  it("omits structure_accession when accession is empty", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({ structuralDiversityEnabled: true, structureAccession: "" }),
    );
    expect(params).not.toHaveProperty("structure_accession");
  });
});

describe("buildEvolveproLoadParams column overrides", () => {
  it("omits variant_column/score_column/sheet_name when all are null (auto-detect)", () => {
    const params = buildEvolveproLoadParams(makeConfig());
    expect(params).not.toHaveProperty("variant_column");
    expect(params).not.toHaveProperty("score_column");
    expect(params).not.toHaveProperty("sheet_name");
  });

  it("sends variant_column/score_column/sheet_name only when explicitly overridden", () => {
    const params = buildEvolveproLoadParams(
      makeConfig({
        evolveproVariantColumn: "mutation",
        evolveproScoreColumn: "fitness",
        evolveproSheetName: "Round 2",
      }),
    );
    expect(params.variant_column).toBe("mutation");
    expect(params.score_column).toBe("fitness");
    expect(params.sheet_name).toBe("Round 2");
  });

  it("always sends score_order regardless of override state", () => {
    const autoParams = buildEvolveproLoadParams(makeConfig());
    expect(autoParams.score_order).toBe("desc");

    const overriddenParams = buildEvolveproLoadParams(
      makeConfig({ evolveproScoreOrder: "asc" }),
    );
    expect(overriddenParams.score_order).toBe("asc");
  });
});

describe("resolveSelectionDomains", () => {
  const referenceDomains = [{ name: "Ref", id: "IPR1", start: 15, end: 25, db: "InterProScan" }];

  it("uses direct reference-sequence annotations", () => {
    expect(resolveSelectionDomains(referenceDomains)).toEqual(referenceDomains);
  });

  it("does not reinterpret accession-frame domains as selection coordinates", () => {
    expect(resolveSelectionDomains(undefined)).toEqual([]);
  });
});

describe("buildEvolveproLoadStateUpdate: a missing prediction is not a fitness", () => {
  function build(
    variants: string[],
    yPreds: (number | undefined)[],
    rankedCandidates: NonNullable<EvolveproLoadResult["ranked_candidates"]> = [],
  ) {
    return buildEvolveproLoadStateUpdate({
      result: {
        variants,
        // The shape the sidecar returns. A short y_preds is what produces the
        // undefined this test is about.
        y_preds: yPreds as number[],
        ranked_candidates: rankedCandidates,
        total_count: variants.length,
        selected_count: variants.length,
      },
      currentMode: "evolvepro",
      maxPerPosition: 5,
      threeDConsumerOn: false,
      structureLoaded: false,
    });
  }

  it("예측이 없는 variant는 항목 자체가 빠진다", () => {
    // 이전에는 `?? 0` 이 0.0 을 넣었다. 이 척도에서 0.0 은 실측 가능한
    // 적합도라 대체값과 측정값을 구별할 수 없었고, 그대로 run_benchmark 의
    // ground_truth 와 benchmark_raw.landscape 로 들어갔다.
    const update = build(["A1V", "B2C"], [0.8, undefined]);
    expect(update.yPredMap).toEqual({ A1V: 0.8 });
    expect("B2C" in update.yPredMap).toBe(false);
  });

  it("진짜 0인 예측은 그대로 남는다", () => {
    // 대조군이자 수정의 핵심. 부재와 0 이 같은 항목으로 합쳐지면 안 된다.
    // 이게 없으면 0 을 전부 버리는 구현도 위 테스트를 통과한다.
    const update = build(["A1V", "B2C"], [0.0, 0.8]);
    expect(update.yPredMap).toEqual({ A1V: 0.0, B2C: 0.8 });
  });

  it("빠진 예측이 없으면 전부 남는다", () => {
    const update = build(["A1V", "B2C"], [0.8, -0.3]);
    expect(update.yPredMap).toEqual({ A1V: 0.8, B2C: -0.3 });
  });

  it("keeps a ranked buffer candidate score when the user selects it later", () => {
    const update = build(
      ["A1V"],
      [0.8],
      [{ variant: "B2C", y_pred: 0, aa_position: 2 }],
    );
    expect(update.yPredMap).toEqual({ B2C: 0, A1V: 0.8 });
  });
});

describe("strict spatial opt-in requests", () => {
  it("pins local prediction identity and hash without accession or legacy selection filters", () => {
    const predictionBundle = { path: "/tmp/prediction.zip", modelId: "job_model_0.cif", chainId: "", sha256: "a".repeat(64) };
    const params = buildEvolveproLoadParams(makeConfig({ structuralDiversityEnabled: true, strictSpatialEnabled: true,
      structureAccession: "P12345", predictionBundle, positionDiversityEnabled: true, paretoDiversityEnabled: true }));
    expect(params).toMatchObject({ prediction_bundle_path: predictionBundle.path, prediction_model_id: predictionBundle.modelId,
      prediction_chain_id: "", prediction_bundle_sha256: predictionBundle.sha256 });
    for (const field of ["structure_accession", "max_per_position", "pareto_diversity", "prediction_bundle_model_id"]) {
      expect(params).not.toHaveProperty(field);
    }
    const legacy = buildEvolveproLoadParams(makeConfig({ predictionBundle }));
    expect(legacy).not.toHaveProperty("prediction_bundle_path");
  });
  it("sends a full-pool request without legacy weighting or narrowing", () => {
    const params = buildEvolveproLoadParams(makeConfig({
      structuralDiversityEnabled: true, strictSpatialEnabled: true,
      paretoDiversityEnabled: true, positionDiversityEnabled: true, domainDiversityEnabled: true,
      anchorVariants: ["F89W"], activeDomains: [{ id: "D1", db: "test", name: "domain", start: 2, end: 30 }],
      structureAccession: "P12345", refSeq: "MAAAA",
    }));
    expect(params).toMatchObject({ strict_spatial: true, structural_diversity: true, structure_accession: "P12345", ref_seq: "MAAAA" });
    expect(params).toMatchObject({ strict_spatial_budget: "unique_sites", strict_spatial_site_cap: null });
    for (const key of ["structural_kappa", "anchor_variants", "max_per_position", "domain_diversity", "pareto_diversity", "pool_multiplier"]) {
      expect(params).not.toHaveProperty(key);
    }
  });
  it("leaves legacy and Top-N requests unchanged unless both opt-ins are active", () => {
    expect(buildEvolveproLoadParams(makeConfig({ strictSpatialEnabled: true }))).not.toHaveProperty("strict_spatial");
    expect(buildEvolveproLoadParams(makeConfig({ strictSpatialEnabled: true, structuralDiversityEnabled: true, usePipeline: false }))).not.toHaveProperty("strict_spatial");
  });
  it.each([null, 19])("forwards the explicit distinct-variant budget and site cap %s", (cap) => {
    const params = buildEvolveproLoadParams(makeConfig({ structuralDiversityEnabled: true, strictSpatialEnabled: true,
      strictSpatialBudgetMode: "distinct_variants", strictSpatialSiteCap: cap, topN: 95 }));
    expect(params).toMatchObject({ top_n: 95, strict_spatial_budget: "distinct_variants", strict_spatial_site_cap: cap });
    expect(params).not.toHaveProperty("max_per_position");
  });
  it.each([1, 12, 95, 100])("forwards user N=%s from the full df_test pool without a fixed experiment size", (count) => {
    const params = buildEvolveproLoadParams(makeConfig({ filepath: "/tmp/synthetic_df_test.csv",
      structuralDiversityEnabled: true, strictSpatialEnabled: true,
      strictSpatialBudgetMode: "distinct_variants", topN: count }));
    expect(params).toMatchObject({ filepath: "/tmp/synthetic_df_test.csv", top_n: count,
      strict_spatial_budget: "distinct_variants", strict_spatial_site_cap: null });
    for (const key of ["max_per_position", "pool_multiplier", "structural_kappa", "domain_diversity", "pareto_diversity"]) {
      expect(params).not.toHaveProperty(key);
    }
  });
  it("keeps a saved distinct cap inactive under the default site budget", () => {
    const params = buildEvolveproLoadParams(makeConfig({ structuralDiversityEnabled: true, strictSpatialEnabled: true,
      strictSpatialBudgetMode: "unique_sites", strictSpatialSiteCap: 19 }));
    expect(params).toMatchObject({ strict_spatial_budget: "unique_sites", strict_spatial_site_cap: null });
  });
});
