import i18next from "i18next";
import type {
  DomainInfo,
  DomainStat,
  EvolveproLoadResult,
  EvolveproStepStats,
} from "../../types/models";
import type { Round } from "../../types/round";

export interface EvolveproLoadConfig {
  filepath: string;
  topN: number;
  usePipeline: boolean;
  /** Mutation/variant column name override (null = backend auto-detect via VARIANT_COLUMNS alias). */
  evolveproVariantColumn: string | null;
  /** Ranking/score column name override (null = backend auto-detect via SCORE_COLUMNS alias). */
  evolveproScoreColumn: string | null;
  /** Score ordering direction; always sent. */
  evolveproScoreOrder: "asc" | "desc";
  /** Sheet name for XLSX files (null = first sheet). */
  evolveproSheetName: string | null;
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  activeDomains: DomainInfo[];
  excludedDomains: DomainInfo[];
  domainDiversityEnabled: boolean;
  domainStrategy: "proportional" | "equal";
  domainOverlapPolicy: "first" | "largest";
  linkerHandling: "include" | "separate-bin" | "exclude";
  domainQuotaMin: number;
  paretoDiversityEnabled: boolean;
  entropyWeightEnabled: boolean;
  entropyWeight: number;
  paretoPoolMultiplier: number;
  distanceMode: "auto" | "1d" | "3d";
  structureAccession: string;
  evolveproRound: number;
  roundSize: number;
  /**
   * Protein reference sequence (1-indexed positions). Used by the kuro
   * sidecar to convert EVOLVEpro short-form variants (`89W`) back to
   * internal notation (`F89W`). Optional — empty string means
   * pass-through (backward compatible).
   */
  refSeq: string;
  structuralDiversityEnabled: boolean;
  structuralKappa: number;
  /**
   * Cumulative already-explored variant IDs (internal notation, e.g. `F89W`)
   * for structural-diversity revealed-anchor maximin. Empty = no anchor
   * (greedy seed is the max-fitness row). Backward compatible.
   */
  anchorVariants: string[];
}

export interface EvolveproLoadStateUpdate {
  mutationText: string;
  yPredMap: Record<string, number>;
  domainStats: Record<string, DomainStat>;
  poolVariants: string[];
  evolveproTotalCount: number;
  evolveproFilteredCount: number | null;
  evolveproParetoExchanges: number | null;
  evolveproStepStats: EvolveproStepStats | null;
  statusMessage: string;
}

export function resolveSelectionDomains(
  refDomains: DomainInfo[] | undefined,
): DomainInfo[] {
  return refDomains ?? [];
}

export function buildEvolveproLoadParams(config: EvolveproLoadConfig): Record<string, unknown> {
  const {
    filepath,
    topN,
    usePipeline,
    evolveproVariantColumn,
    evolveproScoreColumn,
    evolveproScoreOrder,
    evolveproSheetName,
    positionDiversityEnabled,
    maxPerPosition,
    activeDomains,
    excludedDomains,
    domainDiversityEnabled,
    domainStrategy,
    domainOverlapPolicy,
    linkerHandling,
    domainQuotaMin,
    paretoDiversityEnabled,
    entropyWeightEnabled,
    entropyWeight,
    paretoPoolMultiplier,
    distanceMode,
    structureAccession,
    evolveproRound,
    roundSize,
    refSeq,
    structuralDiversityEnabled,
    structuralKappa,
    anchorVariants,
  } = config;

  const params: Record<string, unknown> = {
    filepath,
    top_n: topN,
    ...(evolveproVariantColumn && { variant_column: evolveproVariantColumn }),
    ...(evolveproScoreColumn && { score_column: evolveproScoreColumn }),
    score_order: evolveproScoreOrder,
    ...(evolveproSheetName && { sheet_name: evolveproSheetName }),
    ...(usePipeline && positionDiversityEnabled && { max_per_position: maxPerPosition }),
    ...(usePipeline && excludedDomains.length > 0 && {
      excluded_ranges: excludedDomains.map((d) => ({ start: d.start, end: d.end })),
    }),
    ...(usePipeline && domainDiversityEnabled && activeDomains.length > 0 && {
      domain_diversity: true,
      domains: activeDomains.map((d) => ({ name: d.name, start: d.start, end: d.end })),
      domain_strategy: domainStrategy,
      domain_overlap_policy: domainOverlapPolicy,
      linker_handling: linkerHandling,
      domain_quota_min: domainQuotaMin,
    }),
    ...(usePipeline && paretoDiversityEnabled && { pareto_diversity: true }),
    ...(usePipeline && paretoDiversityEnabled && entropyWeightEnabled && { entropy_weight: entropyWeight }),
    ...(usePipeline && paretoDiversityEnabled && { pool_multiplier: paretoPoolMultiplier }),
    ...(usePipeline && paretoDiversityEnabled && { distance_mode: distanceMode }),
    ...(usePipeline && (paretoDiversityEnabled || structuralDiversityEnabled) && structureAccession && {
      structure_accession: structureAccession,
    }),
    ...(usePipeline && paretoDiversityEnabled && evolveproRound > 0 && {
      evolvepro_round: evolveproRound,
      round_size: roundSize,
    }),
    ...(refSeq && { ref_seq: refSeq }),
    ...(usePipeline && structuralDiversityEnabled && { structural_diversity: true }),
    ...(usePipeline && structuralDiversityEnabled && { structural_kappa: structuralKappa }),
    ...(usePipeline && { anchor_variants: anchorVariants }),
  };
  return params;
}

/**
 * Collect the cumulative set of already-explored variant IDs across every
 * round's merged table, for use as `anchor_variants` in structural-diversity
 * selection. Dedupes (first-seen order), drops null and "WT". The structural
 * selector maximises minimum distance to this set so new picks spread away
 * from sequence space already committed to a plate.
 */
export function collectAnchorVariants(rounds: Round[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const round of rounds) {
    for (const row of round.merged_table) {
      const m = row.mutation;
      if (m && m !== "WT" && !seen.has(m)) {
        seen.add(m);
        out.push(m);
      }
    }
  }
  return out;
}

export function buildEvolveproLoadStateUpdate(params: {
  result: EvolveproLoadResult;
  currentMode: "text" | "evolvepro";
  maxPerPosition: number;
}): EvolveproLoadStateUpdate {
  const { result, maxPerPosition } = params;
  const yPredMap: Record<string, number> = {};
  result.variants.forEach((v, i) => {
    yPredMap[v] = result.y_preds[i] ?? 0;
  });

  const filteredMsg = result.filtered_count
    ? ` (${result.filtered_count} filtered, max ${maxPerPosition}/pos)`
    : "";
  const domainMsg = result.domain_stats
    ? " | " + Object.entries(result.domain_stats)
      .map(([name, s]) => (s.selected < s.quota ? `${name}: ${s.selected}/${s.quota} \u26A0` : `${name}: ${s.selected}/${s.quota}`))
      .join(", ")
    : "";
  const paretoMsg = result.pareto_replaced != null && result.pareto_replaced > 0
    ? ` | Pareto: ${result.pareto_replaced} diversified`
    : "";
  const structureMsg = result.structure_frame_mismatch
    ? ` | ${i18next.t("inputSlice.structureFrameMismatch")}`
    : "";
  const modeLabel = "EVOLVEpro";

  return {
    mutationText: result.variants.join("\n"),
    yPredMap,
    domainStats: result.domain_stats ?? {},
    poolVariants: result.pool_variants ?? [],
    evolveproTotalCount: result.total_count,
    evolveproFilteredCount: result.filtered_count ?? null,
    evolveproParetoExchanges: result.pareto_replaced ?? null,
    evolveproStepStats: result.step_stats ?? null,
    statusMessage: `${modeLabel}: ${result.selected_count}/${result.total_count} variants${filteredMsg}${domainMsg}${paretoMsg}${structureMsg}`,
  };
}
