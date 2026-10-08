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
import type { Round, RoundAdvisoryRecord } from "@/types/round";

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
export function normalizePath(path: string): string {
  return path.replace(/\\/g, "/").toLowerCase();
}

/**
 * What the app knows about the content of a file: when it wrote it.
 *
 * Keyed by normalized path, so a file the operator picked by hand is stamped
 * too whenever that path happens to be one a round produced. Two rounds
 * pointing at the same path leave the later round stamp, which is the state the
 * collision notice in step 4.1 exists to keep the operator out of.
 */
export type RoundOutputStamps = ReadonlyMap<string, string>;

/** Stamp of a file no round produced, so this app cannot vouch for its content. */
const UNSTAMPED = "external";

const NO_STAMPS: RoundOutputStamps = new Map();

/** When each round wrote its EVOLVEpro input, by normalized path. */
export function roundOutputStamps(rounds: Round[]): RoundOutputStamps {
  const stamps = new Map<string, string>();
  for (const round of rounds) {
    const artifact = round.evolvepro_input;
    if (artifact?.path && artifact.produced_at) {
      stamps.set(normalizePath(artifact.path), artifact.produced_at);
    }
  }
  return stamps;
}

/**
 * The EVOLVEpro inputs the rounds have produced, oldest round first.
 *
 * Round numbers are preserved rather than renumbered: the handler sorts by `n`
 * and counts entries, so a gap (a round that produced nothing) still orders
 * correctly and does not inflate the round count.
 *
 * Each entry also carries the wild-type replicates its build recorded, which
 * is what lets the classifier run the bootstrap behind switch_combinatorial
 * and stop. The workbook itself has no room for them, so this is the only way
 * they reach step 4.2. A round that recorded none contributes the file alone;
 * that costs nothing until the signals propose a transition, and only then
 * does the handler answer that the question could not be put.
 */
export function roundEvolveproFiles(rounds: Round[]): RoundFileEntry[] {
  const produced: RoundFileEntry[] = [];
  for (const round of rounds) {
    const artifact = round.evolvepro_input;
    if (!artifact?.path) continue;
    const entry: RoundFileEntry = { n: round.n, path: artifact.path };
    if (artifact.wt_values?.length) entry.wt_values = artifact.wt_values;
    if (artifact.variant_replicates && Object.keys(artifact.variant_replicates).length) {
      entry.variant_replicates = artifact.variant_replicates;
    }
    produced.push(entry);
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
 * Stable identity of a classifier input list, contents included.
 *
 * A stored verdict is only about the files it was computed from, so restoring
 * one has to be able to tell whether the list on screen is still that list.
 * Order is normalised by round number because the handler sorts the same way.
 *
 * Paths alone do not identify the files. Step 4.1 derives its destination from
 * the round number, so rebuilding a round writes the same path with different
 * numbers in it; a path-only identity would hand the operator an answer about
 * the previous build and call it current. Each entry therefore carries the
 * moment the app wrote that file (`Round.evolvepro_input.produced_at`), which
 * a rebuild moves.
 *
 * A file this app did not write carries `UNSTAMPED` instead: there is nothing
 * recorded to compare, and the alternative (reading size and mtime off the
 * filesystem) cannot serve the callers that decide step completion, since those
 * run synchronously while rendering and at hydration. Those entries are matched
 * on path alone and the card says so rather than claiming they were verified.
 *
 * Signatures written before stamps existed match nothing here, so verdicts
 * stored by an earlier build of this branch read as history. That is the safe
 * direction: the operator is asked to run again rather than shown an answer
 * this code cannot vouch for.
 */
export function roundFilesSignature(
  files: RoundFileEntry[],
  stamps: RoundOutputStamps,
): string {
  return files
    .slice()
    .sort((a, b) => a.n - b.n)
    .map((entry) => {
      const path = normalizePath(entry.path);
      return `${entry.n}:${path}@${stamps.get(path) ?? UNSTAMPED}`;
    })
    .join("|");
}

/** Identity of the same list ignoring contents: round numbers and paths only. */
export function roundFilesPathSignature(files: RoundFileEntry[]): string {
  return roundFilesSignature(files, NO_STAMPS);
}

/** The entries no round produced, which is what the app cannot confirm unchanged. */
export function unstampedFiles(
  files: RoundFileEntry[],
  stamps: RoundOutputStamps,
): RoundFileEntry[] {
  return files.filter((entry) => !stamps.has(normalizePath(entry.path)));
}

/**
 * Whether the round outputs still hold what `record` was computed from.
 *
 * The check is made against the record own inputs rather than any list on
 * screen, so it answers the same way wherever it is asked: while the card is
 * mounted, in the workflow rail, and right after a restart before any of step 4
 * has been opened.
 */
export function isAdvisoryCurrent(
  record: RoundAdvisoryRecord,
  stamps: RoundOutputStamps,
): boolean {
  return roundFilesSignature(record.inputs, stamps) === record.input_signature;
}

/**
 * The advisory answer on record for the active round, or null when there is
 * none or the files behind it have been rebuilt since.
 *
 * This is the one place that decides whether an answer counts as the current
 * one. Step completion (lib/mame/mameStepCompletion.ts) and the card both read
 * it, so neither can call the step finished on an answer the other treats as
 * history.
 */
export function currentRoundAdvisory(
  rounds: Round[],
  activeRoundId: string | null,
): RoundAdvisoryRecord | null {
  const record = rounds.find((r) => r.id === activeRoundId)?.advisory ?? null;
  if (!record) return null;
  return isAdvisoryCurrent(record, roundOutputStamps(rounds)) ? record : null;
}
