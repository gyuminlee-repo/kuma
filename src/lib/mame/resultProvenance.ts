/**
 * resultProvenance.ts — whether a saved run is this build's answer.
 *
 * A finished analyze is persisted verbatim (`.autosave/mame-result.json`) and
 * replayed on restore, which is what makes a project survive weeks of
 * sequencing turnaround. That replay is right whenever the two builds agree
 * about what a run produces, and wrong when they do not: it would put another
 * engine's verdicts on screen as this build's answer.
 *
 * Whether they agree is decided by `resultContract.ts`, a revision that moves
 * only when the meaning of a result moves. A release that changed a panel or a
 * translation leaves the revision alone, so the run restores exactly as before
 * and the operator is never asked to re-analyse for nothing.
 *
 * When the revisions differ the caller does not soften it into a warning: the
 * result is not shown and a re-run is the way back. There is no "keep reading
 * it anyway", because an app that lets you keep reading it is telling you to
 * trust it. The saved file itself is never touched.
 */

import {
  RESULT_CONTRACT,
  changesSince,
  compareVersionParts,
  revisionForVersion,
  type ResultContractRevision,
} from "./resultContract";

/**
 * How a saved result relates to what this build would produce.
 *
 * - `same`: same result contract. Restores untouched, whatever the versions say.
 * - `older`: produced before one or more result-affecting changes.
 * - `newer`: produced at a contract this build does not implement.
 * - `unknown`: neither a contract nor a parseable version was recorded, so the
 *   origin cannot be established. Suspect rather than trusted.
 */
export type ResultVersionRelation = "same" | "older" | "newer" | "unknown";

/**
 * Compare two dotted numeric versions. Exported because the version, not the
 * revision, is what the operator is shown.
 */
export function compareVersions(left: number[], right: number[]): number {
  return compareVersionParts(left, right);
}

/**
 * Classify a saved result against this build.
 *
 * `contract` is authoritative when present: the producer stamped it for its own
 * result semantics. Snapshots written before that field existed fall back to
 * the revision that was current at their version, so an old project is still
 * judged by behaviour. Only when neither can be established is the origin
 * unknown, and unknown is treated as suspect.
 */
export function classifyResultVersion(
  recorded: string | null | undefined,
  current: string,
  contract?: number | null,
): ResultVersionRelation {
  if (typeof contract === "number" && Number.isInteger(contract)) {
    if (contract === RESULT_CONTRACT) return "same";
    return contract < RESULT_CONTRACT ? "older" : "newer";
  }
  if (typeof recorded !== "string") return "unknown";
  // An exact version match settles it before any parsing: a build string is not
  // always a dotted number (a dev or CI build can carry a suffix), and a
  // snapshot written by the very build now reading it is the same run.
  if (recorded.trim().length > 0 && recorded.trim() === current.trim()) return "same";
  const recordedRevision = revisionForVersion(recorded);
  if (recordedRevision === null) return "unknown";
  const target = contractOf(current);
  if (recordedRevision === target) return "same";
  return recordedRevision < target ? "older" : "newer";
}

/**
 * The contract a build of `current` produces. Normally `RESULT_CONTRACT`, since
 * that is what this build stamps; derived from the release table when the
 * caller names a different build, which is what makes the comparison meaningful
 * for any pair of versions rather than only for the running one.
 */
function contractOf(current: string): number {
  return revisionForVersion(current) ?? RESULT_CONTRACT;
}

/**
 * What a saved result was produced by, when this build will not show it. Null
 * whenever the contracts match, which includes every release that changed
 * nothing about results.
 */
export interface RestoredResultProvenance {
  /** The recorded version, or null when the snapshot carried none. */
  version: string | null;
  /**
   * The contract the result was produced at: stamped by its producer, or
   * derived from its version. Null when neither could be established.
   */
  contract: number | null;
  relation: Exclude<ResultVersionRelation, "same">;
  /**
   * The result-affecting changes this build has and the saved run does not,
   * oldest first: the reason a re-run is being asked for. Empty for a `newer`
   * or `unknown` origin, where this build cannot enumerate what the other did.
   */
  changes: ResultContractRevision[];
}

/**
 * The store value for a saved result: null when it matches this build's
 * contract and can be restored as-is, otherwise the origin to state on screen.
 * Both restore paths (the result file and the input-snapshot fallback) go
 * through here so the two cannot drift apart.
 */
export function provenanceFor(
  version: string | null | undefined,
  current: string,
  contract?: number | null,
): RestoredResultProvenance | null {
  const relation = classifyResultVersion(version, current, contract);
  if (relation === "same") return null;
  const resolved =
    typeof contract === "number" && Number.isInteger(contract)
      ? contract
      : revisionForVersion(version);
  const target = revisionForVersion(current) ?? RESULT_CONTRACT;
  return {
    version: version ?? null,
    contract: resolved,
    relation,
    changes:
      relation === "older" && resolved !== null
        ? changesSince(resolved).filter((change) => change.revision <= target)
        : [],
  };
}

export { RESULT_CONTRACT, changesSince, revisionForVersion };
