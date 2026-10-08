/**
 * The export rounds of the current design, shared by the export form and the
 * plate preview so both split the selection the same way.
 *
 * A selection of one plate or less is not split (`roundMode` false, `rounds`
 * empty) and every export path behaves as it did before rounds existed.
 * Anything past one plate is split, however many rounds it takes.
 */
import { useMemo } from "react";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "@/store/appStore";
import { getSortedMutations } from "@/lib/plate-utils";
import {
  fitRoundPicks,
  needsRounds,
  splitIntoRounds,
  type PlateRound,
  type RoundPicks,
} from "@/lib/plateRounds";

export interface ExportRounds {
  wellCount: number;
  roundMode: boolean;
  rounds: PlateRound[];
  /**
   * The stored round picks fitted to these rounds (`fitRoundPicks`). Read
   * these, not `echoRoundPicks`, so a plate the picker does not offer is never
   * shown blank and sent anyway. Empty outside round mode.
   */
  picks: RoundPicks;
  /** True when `picks` differs from the store, which should then be written back. */
  picksStale: boolean;
}

export function useExportRounds(): ExportRounds {
  const { designResults, plateMappings, dedupInfo, tableSorting, yPredMap, customCandidates, storedPicks } =
    useAppStore(
      useShallow((s) => ({
        designResults: s.designResults,
        plateMappings: s.plateMappings,
        dedupInfo: s.dedupInfo,
        tableSorting: s.tableSorting,
        yPredMap: s.yPredMap,
        customCandidates: s.customCandidates,
        storedPicks: s.echoRoundPicks,
      })),
    );
  const wellCount = designResults.length;
  const roundMode = needsRounds(wellCount);
  const rounds = useMemo(() => {
    if (!roundMode) return [];
    // The order the result table shows, the same one a single-plate export uses.
    const sortedMuts = getSortedMutations(designResults, tableSorting, {
      yPredMap,
      customCandidates,
    });
    return splitIntoRounds(plateMappings, dedupInfo, sortedMuts);
  }, [roundMode, designResults, tableSorting, yPredMap, customCandidates, plateMappings, dedupInfo]);
  const picks = useMemo(
    () => (roundMode ? fitRoundPicks(storedPicks, rounds.length) : []),
    [roundMode, storedPicks, rounds.length],
  );
  return { wellCount, roundMode, rounds, picks, picksStale: roundMode && picks !== storedPicks };
}
