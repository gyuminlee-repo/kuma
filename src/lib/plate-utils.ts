/**
 * Shared plate mapping utilities used by PlateMap UI and Excel export.
 */
import type { PlateMapping, SdmPrimerResult } from "../types/models";
import type { SortingState } from "@tanstack/react-table";

const ROWS = "ABCDEFGH";

function wellName(idx: number): string {
  const col = Math.floor(idx / 8) + 1;
  const row = idx % 8;
  return `${ROWS[row]}${col}`;
}

/**
 * Canonical sort: returns sorted SdmPrimerResult[] preserving per-row identity.
 * Tiebreaker uses the row object's original array index (not mutation string),
 * so duplicate mutations at the same sort-key position are ordered stably.
 * Returns null if no sort is active.
 *
 * This is the single source-of-truth for primer ordering used by all step5
 * views (ResultTable, PlateMap, Mapping File Preview / Export).
 */
export function sortPrimersCanonical(
  results: SdmPrimerResult[],
  sorting: SortingState,
  options?: {
    yPredMap?: Record<string, number>;
    customCandidates?: Record<string, SdmPrimerResult[]>;
  },
): SdmPrimerResult[] | null {
  if (sorting.length === 0) return null;
  const sort = sorting[0];
  const yPredMap = options?.yPredMap ?? {};
  const customCandidates = options?.customCandidates ?? {};

  type R = SdmPrimerResult;
  // Key by object identity so duplicate mutation strings each get their own index.
  const originalIndex = new Map<R, number>(results.map((r, i) => [r, i]));

  const numericKeys: Record<string, (r: R) => number> = {
    mutation: (r) => r.aa_position ?? 0,
    y_pred: (r) => yPredMap[r.mutation] ?? -Infinity,
    fwd_len: (r) => r.fwd_len,
    rev_len: (r) => r.rev_len,
    tm_no_fwd: (r) => r.tm_no_fwd,
    tm_no_rev: (r) => r.tm_no_rev,
    tm_overlap: (r) => r.tm_overlap,
    tolerance_used: (r) => r.tolerance_used,
    penalty: (r) => r.penalty,
    gc_fwd: (r) => r.gc_fwd,
    gc_rev: (r) => r.gc_rev,
    has_offtarget: (r) => r.has_offtarget ? 1 : 0,
    hairpin: (r) => Math.max(r.hairpin_tm_fwd ?? 0, r.hairpin_tm_rev ?? 0, r.homodimer_tm_fwd ?? 0, r.homodimer_tm_rev ?? 0),
    candidate_count: (r) => {
      const customLen = (customCandidates[r.mutation] ?? []).length;
      return Math.max(
        (r.candidate_fwd_count ?? 0) + customLen,
        (r.candidate_rev_count ?? 0) + customLen,
      );
    },
    synth: (r) => Math.min(r.synthesis_score_fwd ?? 100, r.synthesis_score_rev ?? 100),
  };
  const stringKeys: Record<string, (r: R) => string> = {
    wt_codon: (r) => r.wt_codon ?? "",
    mt_codon: (r) => r.mt_codon ?? "",
  };

  const getter = numericKeys[sort.id];
  const stringGetter = stringKeys[sort.id];
  if (!getter && !stringGetter) return null;

  const direction = sort.desc ? -1 : 1;
  return [...results].sort((a, b) => {
    if (getter) {
      const diff = getter(a) - getter(b);
      if (diff !== 0) return diff * direction;
    } else if (stringGetter) {
      const diff = stringGetter(a).localeCompare(stringGetter(b));
      if (diff !== 0) return diff * direction;
    }
    // Tiebreaker: original array index (per-row, not per-mutation-string).
    return (originalIndex.get(a) ?? 0) - (originalIndex.get(b) ?? 0);
  });
}

/**
 * Compute sorted mutation order from designResults + tableSorting.
 * Thin wrapper over sortPrimersCanonical that deduplicates to unique mutation
 * strings in canonical order (first occurrence wins).
 * Returns null if no sort is active.
 * Callers (PlateMap, ExportPlatePreview, exportSlice, export-handlers) are unchanged.
 */
export function getSortedMutations(
  results: SdmPrimerResult[],
  sorting: SortingState,
  options?: {
    yPredMap?: Record<string, number>;
    customCandidates?: Record<string, SdmPrimerResult[]>;
  },
): string[] | null {
  const sorted = sortPrimersCanonical(results, sorting, options);
  if (!sorted) return null;
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of sorted) {
    if (!seen.has(r.mutation)) {
      seen.add(r.mutation);
      out.push(r.mutation);
    }
  }
  return out;
}

/**
 * Reorder plate mappings by sorted mutation order with multi-plate support.
 * - Fwd: reordered by sortedMutations, wells reassigned per 96-well plate
 * - Rev: paired per fwd plate (only rev for that plate's mutations), deduplicated
 * - Returns interleaved [...fwdPlate1, ...revPlate1, ...fwdPlate2, ...revPlate2, ...]
 * - If sortedMutations is null, returns original mappings unchanged.
 */
export function reorderMappings(
  mappings: PlateMapping[],
  dedupInfo: Record<string, string[]>,
  sortedMutations: string[] | null,
): PlateMapping[] {
  if (!sortedMutations || sortedMutations.length === 0) return mappings;

  const fwdAll: PlateMapping[] = [];
  const revAll: PlateMapping[] = [];
  for (const mapping of mappings) {
    if (mapping.primer_type === "forward") {
      fwdAll.push(mapping);
    } else {
      revAll.push(mapping);
    }
  }

  // Reorder fwd by sorted mutations
  const fwdByMut = new Map<string, PlateMapping>();
  for (const m of fwdAll) fwdByMut.set(m.mutation, m);
  const allFwd: PlateMapping[] = [];
  const sortedMutationSet = new Set(sortedMutations);
  for (const mut of sortedMutations) {
    const m = fwdByMut.get(mut);
    if (m) allFwd.push(m);
  }
  // Include any fwd not in sortedMutations (e.g. custom additions)
  for (const m of fwdAll) {
    if (!sortedMutationSet.has(m.mutation)) allFwd.push(m);
  }

  // Rev lookup: sequence → PlateMapping, mutation → rev sequence
  const revBySeq = new Map<string, PlateMapping>();
  for (const r of revAll) revBySeq.set(r.sequence, r);
  const mutToRevSeq = new Map<string, string>();
  for (const [seq, muts] of Object.entries(dedupInfo)) {
    for (const mut of muts) mutToRevSeq.set(mut, seq);
  }

  // Chunk fwd by 96, pair rev per chunk
  const result: PlateMapping[] = [];
  for (let start = 0; start < allFwd.length; start += 96) {
    const fwdChunk = allFwd.slice(start, start + 96);

    // Assign fwd wells (0-based per plate)
    for (let i = 0; i < fwdChunk.length; i++) {
      result.push({ ...fwdChunk[i], well: wellName(i) });
    }

    // Collect rev for this chunk's mutations (deduplicated, fwd order)
    const seenRevSeq = new Set<string>();
    let revIdx = 0;
    for (const fwd of fwdChunk) {
      const revSeq = mutToRevSeq.get(fwd.mutation);
      if (revSeq && !seenRevSeq.has(revSeq)) {
        seenRevSeq.add(revSeq);
        const rev = revBySeq.get(revSeq);
        if (rev) result.push({ ...rev, well: wellName(revIdx++) });
      }
    }
  }

  return result;
}

export { wellName };
