/**
 * What each round produced, kept where the app already remembers rounds.
 *
 * Step 4.1 writes one EVOLVEpro input xlsx per round and step 4.2 reads a
 * series of them, so something has to hold the series.
 *
 * The workspace manifest cannot. Its dedupe key is `app::step::type`
 * (lib/workspace/api.ts), one slot per artifact type, and registering round 2
 * deletes the round 1 entry. That is by design: the manifest is a pointer to
 * the newest file of each kind for cross-app handoff, and widening its key
 * would change a schema KURO writes to as well, for a MAME-only need. It also
 * carries no round number, so a series rebuilt from it would have to invent one
 * from timestamps.
 *
 * The round store already is the history. `Round.n` is the round number the
 * classifier takes, and `rounds[]` rides in the mame autosave snapshot
 * (lib/mame/autosaveSnapshot.ts) and in the KURO workspace snapshot
 * (schema_version 0.3), so it survives a restart with no new plumbing. Analyze
 * set the precedent by filing its verdict xlsx on the round
 * (store/mame/slices/inputSlice.ts, persistRoundAnalyzeEvidence), which step
 * 4.1 then prefills from.
 */

import type { RoundFileEntry } from "@/types/mame/strategy";
import type { Round } from "@/types/round";

/** Project subfolder step 4.1 writes into. */
export const EVOLVEPRO_INPUT_FOLDER = "activity";

/**
 * Default output filename for one round.
 *
 * Before this carried the round number every round wrote `evolvepro_input.xlsx`
 * and each build silently replaced the previous round file, which is exactly
 * the series step 4.2 needs to read back.
 */
export function evolveproInputFilename(n: number): string {
  return `evolvepro_input_r${n}.xlsx`;
}

/** Compare paths the way the filesystems under this app do: separators and case folded. */
function normalizePath(path: string): string {
  return path.replace(/\\/g, "/").toLowerCase();
}

/**
 * The EVOLVEpro inputs the rounds have produced, oldest round first.
 *
 * Round numbers are preserved rather than renumbered: the handler sorts by `n`
 * and counts entries, so a gap (a round that produced nothing) still orders
 * correctly and does not inflate the round count.
 */
export function roundEvolveproFiles(rounds: Round[]): RoundFileEntry[] {
  const produced: RoundFileEntry[] = [];
  for (const round of rounds) {
    const path = round.evolvepro_input?.path;
    if (path) produced.push({ n: round.n, path });
  }
  return produced.sort((a, b) => a.n - b.n);
}

/**
 * The round, other than `exceptRoundId`, that already recorded `path` as its
 * output. Building over it would leave that round entry pointing at a file
 * holding another round measurements.
 */
export function roundOwningOutput(
  rounds: Round[],
  path: string,
  exceptRoundId: string | null,
): Round | null {
  if (!path) return null;
  const target = normalizePath(path);
  for (const round of rounds) {
    if (round.id === exceptRoundId) continue;
    const owned = round.evolvepro_input?.path;
    if (owned && normalizePath(owned) === target) return round;
  }
  return null;
}

/**
 * Stable identity of a classifier input list.
 *
 * A stored verdict is only about the files it was computed from, so restoring
 * one has to be able to tell whether the list on screen is still that list.
 * Order is normalised by round number because the handler sorts the same way.
 */
export function roundFilesSignature(files: RoundFileEntry[]): string {
  return files
    .slice()
    .sort((a, b) => a.n - b.n)
    .map((entry) => `${entry.n}:${normalizePath(entry.path)}`)
    .join("|");
}
