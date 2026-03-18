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
 * Compute sorted mutation order from designResults + tableSorting.
 * Returns null if no mutation sort is active.
 */
export function getSortedMutations(
  results: SdmPrimerResult[],
  sorting: SortingState,
): string[] | null {
  if (sorting.length === 0) return null;
  const sort = sorting[0];
  if (sort.id !== "mutation") return null;
  const sorted = [...results].sort(
    (a, b) => (a.aa_position ?? 0) - (b.aa_position ?? 0),
  );
  if (sort.desc) sorted.reverse();
  return sorted.map((r) => r.mutation);
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

  const fwdAll = mappings.filter((m) => m.primer_type === "forward");
  const revAll = mappings.filter((m) => m.primer_type === "reverse");

  // Reorder fwd by sorted mutations
  const fwdByMut = new Map<string, PlateMapping>();
  for (const m of fwdAll) fwdByMut.set(m.mutation, m);
  const allFwd: PlateMapping[] = [];
  for (const mut of sortedMutations) {
    const m = fwdByMut.get(mut);
    if (m) allFwd.push(m);
  }
  // Include any fwd not in sortedMutations (e.g. custom additions)
  for (const m of fwdAll) {
    if (!sortedMutations.includes(m.mutation)) allFwd.push(m);
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
