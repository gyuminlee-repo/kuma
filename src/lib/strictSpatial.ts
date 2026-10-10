import type { AppState } from "@/store/types";
import type { StrictSpatialResult } from "@/types/models";

export function isStrictSpatialMode(state: Pick<AppState, "strictSpatialEnabled" | "structuralDiversityEnabled" | "evolveproMode" | "mutationInputMode">): boolean {
  return Boolean(state.strictSpatialEnabled && state.structuralDiversityEnabled
    && state.evolveproMode !== "topN" && state.mutationInputMode === "evolvepro");
}

/** Bind a certificate to the reference, source, candidate file and selection controls. */
export function strictSpatialContextKey(state: AppState): string {
  const gene = state.seqInfo?.genes.find((g) => String(g.cds_start) === state.selectedGene)
    ?? state.seqInfo?.genes[0];
  return JSON.stringify([
    state.evolveproCsvPath, state.evolveproVariantColumn, state.evolveproScoreColumn,
    state.evolveproScoreOrder, state.evolveproSheetName,
    state.predictionBundleRevision,
    state.strictStructureSource === "prediction_bundle"
      ? ["prediction_bundle", state.predictionBundlePath, state.predictionBundleInventory?.bundle_sha256,
        state.predictionBundleModelId, state.predictionBundleChainId]
      : ["accession", state.structureAccession || state.uniprotAccession],
    gene?.translation ?? "", state.maxPrimers,
    state.strictSpatialBudgetMode, state.strictSpatialSiteCap,
  ]);
}

export function sameVariantIds(a: string[], b: string[]): boolean {
  const bIds = new Set(b);
  return a.length === b.length && new Set(a).size === a.length
    && bIds.size === b.length && a.every((value) => bIds.has(value));
}

export function currentStrictSpatialResult(state: AppState): StrictSpatialResult | null {
  const selection = state.strictSpatialSelection;
  if (!isStrictSpatialMode(state) || !selection
    || selection.contextKey !== strictSpatialContextKey(state)
    || selection.result.budget_mode !== state.strictSpatialBudgetMode
    || selection.result.site_cap !== (state.strictSpatialBudgetMode === "distinct_variants" ? state.strictSpatialSiteCap : null)
    || !sameVariantIds(selection.result.selected_variants, state.evolveproSelectedVariants)) return null;
  const imported = selection.result.prediction_bundle;
  if (state.strictStructureSource === "prediction_bundle"
    ? !imported || imported.bundle_sha256 !== state.predictionBundleInventory?.bundle_sha256
      || imported.model_id !== state.predictionBundleModelId || imported.chain_id !== state.predictionBundleChainId
    : Boolean(imported)) return null;
  return selection.result;
}

