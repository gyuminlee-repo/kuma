import { describe, it, expect } from "vitest";
import {
  buildEvolveproLoadParams,
  collectAnchorVariants,
  type EvolveproLoadConfig,
} from "./inputSlice.helpers";
import type { Round } from "@/types/round";
import type { MergedRow } from "@/types/mame/activity";

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
    evolveproMode: "pipeline",
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
      makeConfig({ usePipeline: false, evolveproMode: "topN", anchorVariants: ["F89W"] }),
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
