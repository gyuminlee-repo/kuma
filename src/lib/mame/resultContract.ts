/**
 * resultContract.ts — the revision of "what an analyze run produces".
 *
 * A saved run is only obsolete when this build would score it differently.
 * Version strings are a bad proxy for that: of the twenty releases in the 0.15
 * line, five changed what a run produces and the rest moved a panel, added a
 * translation or fixed a docs link. Treating every version difference as a
 * stale result would hide a perfectly current run behind a re-run demand, and
 * an hour of re-analysis is a real cost to charge for a CSS fix.
 *
 * So the signal is a revision that moves only when the meaning of a result
 * moves. Each entry names the release it shipped in and what changed, which is
 * also what the screen shows: an operator being told to spend an hour re-running
 * is owed the reason.
 *
 * Adding a revision is part of changing analyze behaviour, not paperwork after
 * it: `.cross-layer-sync.json` ties this file to the analyze handlers and the
 * verdict models, and `resultContract.test.ts` fails if the table stops being
 * ordered or stops agreeing with `RESULT_CONTRACT`.
 */

export interface ResultContractRevision {
  /** Monotonic revision number. */
  revision: number;
  /** The release whose runs are the first to carry this revision. */
  since: string;
  /**
   * What changed about the result, from the operator's side. The value is the
   * i18n key under `mame.restoredResult.change.*`; this table is the record of
   * why the revision exists.
   */
  key: string;
}

/**
 * Revision history, oldest first. `since` lets a snapshot that recorded only a
 * version be mapped back onto the revision that was current when it was written,
 * which is how projects made before this file are judged by behaviour rather
 * than by release cadence.
 */
export const RESULT_CONTRACT_REVISIONS: readonly ResultContractRevision[] = [
  { revision: 1, since: "0.15.10", key: "plateDisagreementRefused" },
  { revision: 2, since: "0.15.13", key: "replicatePurityOrder" },
  { revision: 3, since: "0.15.15", key: "selfConsistencyCheck" },
  { revision: 4, since: "0.15.17.03", key: "plateColumnRowOrder" },
  { revision: 5, since: "0.15.19", key: "barcodePlateShapeRefused" },
] as const;

/** The revision this build's analyze produces. */
export const RESULT_CONTRACT =
  RESULT_CONTRACT_REVISIONS[RESULT_CONTRACT_REVISIONS.length - 1]!.revision;

/** Dotted numeric version as a comparable tuple; null when not parseable. */
export function parseVersionParts(value: string): number[] | null {
  const trimmed = value.trim().replace(/^v/i, "");
  if (trimmed.length === 0) return null;
  const parts = trimmed.split(".");
  const numbers: number[] = [];
  for (const part of parts) {
    // `03` is a real segment in this project's history: parse decimally and
    // reject anything non-numeric rather than guessing.
    if (!/^\d+$/.test(part)) return null;
    numbers.push(Number.parseInt(part, 10));
  }
  return numbers.length > 0 ? numbers : null;
}

/** Compare dotted numeric versions; missing trailing segments count as 0. */
export function compareVersionParts(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index++) {
    const a = left[index] ?? 0;
    const b = right[index] ?? 0;
    if (a !== b) return a < b ? -1 : 1;
  }
  return 0;
}

/**
 * The revision a build of `version` produced, for snapshots written before the
 * revision itself was recorded. Null when the version cannot be parsed, which
 * is the case that has to stay suspect rather than be assumed current.
 *
 * A version older than the first entry maps to revision 0: it predates every
 * recorded change, which is the strongest reason to re-run.
 */
export function revisionForVersion(version: string | null | undefined): number | null {
  if (typeof version !== "string") return null;
  const parts = parseVersionParts(version);
  if (!parts) return null;
  let revision = 0;
  for (const entry of RESULT_CONTRACT_REVISIONS) {
    const since = parseVersionParts(entry.since);
    if (!since) continue;
    if (compareVersionParts(parts, since) >= 0) revision = entry.revision;
  }
  return revision;
}

/** The result-affecting changes made after `revision`, oldest first. */
export function changesSince(revision: number): ResultContractRevision[] {
  return RESULT_CONTRACT_REVISIONS.filter((entry) => entry.revision > revision);
}
