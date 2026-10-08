import type { SortingState } from "@tanstack/react-table";
import type { PlateMapping, SdmPrimerResult } from "@/types/models";
import { getSortedMutations, reorderMappings } from "@/lib/plate-utils";
import { needsRounds, splitIntoRounds } from "@/lib/plateRounds";

/** Pad the display only; the mapping's actual well is never modified. */
function displayWell(well: string): string | undefined {
  const match = /^((?:P[1-9][0-9]*-)?)([A-H])([1-9]|1[0-2])$/.exec(well);
  return match ? `${match[1]}${match[2]}${match[3].padStart(2, "0")}` : undefined;
}

/**
 * Forward-primer well identities from the exact layout used by export_all.
 * Table sorting is an export-layout setting in KURO. Display-only filtering,
 * pagination or row reordering must instead read this map by result identity.
 *
 * Never calculate a physical well from a table row index: mappings can have a
 * different source order, custom additions, or only one selected candidate for
 * a mutation. Unmapped/ambiguous rows have no well rather than a guessed one.
 */
export function buildResultWellMap(
  results: SdmPrimerResult[],
  mappings: PlateMapping[],
  dedupInfo: Record<string, string[]>,
  sorting: SortingState,
  options?: {
    yPredMap?: Record<string, number>;
    customCandidates?: Record<string, SdmPrimerResult[]>;
  },
): Map<SdmPrimerResult, string> {
  const sortedMutations = getSortedMutations(results, sorting, options);
  const layouts = needsRounds(results.length)
    ? splitIntoRounds(mappings, dedupInfo, sortedMutations)
        .map((round) => ({ prefix: `${round.label}: `, mappings: round.mappings }))
    : [{ prefix: "", mappings: reorderMappings(mappings, dedupInfo, sortedMutations) }];
  const byMutation = new Map<string, Map<string, string[]>>();
  for (const layout of layouts) {
    for (const mapping of layout.mappings) {
      if (mapping.primer_type !== "forward") continue;
      const well = displayWell(mapping.well);
      if (!well) continue;
      const bySequence = byMutation.get(mapping.mutation) ?? new Map<string, string[]>();
      const wells = bySequence.get(mapping.sequence) ?? [];
      wells.push(`${layout.prefix}${well}`);
      bySequence.set(mapping.sequence, wells);
      byMutation.set(mapping.mutation, bySequence);
    }
  }
  const labels = new Map<SdmPrimerResult, string>();
  for (const result of results) {
    const wells = byMutation.get(result.mutation)?.get(result.forward_seq);
    if (wells?.length === 1) labels.set(result, wells[0]);
  }
  return labels;
}
