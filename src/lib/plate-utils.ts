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
 * Reorder plate mappings by sorted mutation order.
 * - Fwd: reordered by sortedMutations, wells reassigned
 * - Rev: deduplicated in fwd-first-occurrence order, wells reassigned
 * - Returns [...fwd, ...rev] flat array
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

  // Reorder fwd
  const fwdByMut = new Map<string, PlateMapping>();
  for (const m of fwdAll) fwdByMut.set(m.mutation, m);
  const orderedFwd: PlateMapping[] = [];
  for (const mut of sortedMutations) {
    const m = fwdByMut.get(mut);
    if (m) orderedFwd.push({ ...m, well: wellName(orderedFwd.length) });
  }
  // Include any fwd not in sortedMutations (e.g. custom additions)
  for (const m of fwdAll) {
    if (!sortedMutations.includes(m.mutation)) {
      orderedFwd.push({ ...m, well: wellName(orderedFwd.length) });
    }
  }

  // Reorder rev: deduplicate in order of first fwd occurrence
  const seenRevSeq = new Map<string, PlateMapping>();
  for (const fwd of orderedFwd) {
    const rev = revAll.find((r) => dedupInfo[r.sequence]?.includes(fwd.mutation));
    if (rev && !seenRevSeq.has(rev.sequence)) {
      seenRevSeq.set(rev.sequence, rev);
    }
  }
  let revIdx = 0;
  const orderedRev = [...seenRevSeq.values()].map((m) => ({
    ...m,
    well: wellName(revIdx++),
  }));

  return [...orderedFwd, ...orderedRev];
}

export { wellName };
