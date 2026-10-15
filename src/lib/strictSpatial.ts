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
    state.structureAccession || state.uniprotAccession, gene?.translation ?? "", state.maxPrimers,
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
    || !sameVariantIds(selection.result.selected_variants, state.evolveproSelectedVariants)) return null;
  return selection.result;
}

