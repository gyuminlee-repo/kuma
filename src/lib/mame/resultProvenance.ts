/**
 * resultProvenance.ts — whose engine produced the result now on screen.
 *
 * A finished analyze is persisted verbatim (`.autosave/mame-result.json`) and
 * replayed on restore, which is what makes a project survive weeks of
 * sequencing turnaround. The replay is faithful to a fault: it reinstates
 * verdicts, the plate and the summary exactly as they were written, and the
 * screen then presents them as though the running build had just produced them.
 *
 * That is wrong whenever the two builds disagree. Between v0.15.10 and
 * v0.15.17 alone, MAME learned to refuse a workbook that writes one plate two
 * ways, to order replicate picks by measured purity, to check a finished run
 * against itself, and to order result rows down the plate column. A result
 * scored before those changes is not what this build would produce, and
 * nothing on screen said so.
 *
 * The snapshot already records `kuma_version`; this module is the missing half
 * that reads it. It only classifies. Deciding what to do with the answer (a
 * notice, a re-run, or nothing) belongs to the caller, because discarding an
 * operator's saved run or launching a long analysis unasked are both worse
 * than showing a stale result with its provenance stated.
 */

/**
 * How the version that wrote a restored result relates to the running build.
 *
 * - `same`: written by this build. Nothing to say.
 * - `older`: written by an earlier build, so current fixes are missing from it.
 * - `newer`: written by a later build; this one may not score the same way.
 * - `unknown`: no usable version was recorded (a snapshot from before the field
 *   existed, or a malformed value). Treated as suspect rather than trusted.
 */
export type ResultVersionRelation = "same" | "older" | "newer" | "unknown";

/** A dotted numeric version, e.g. `0.15.17.03`, as a comparable tuple. */
function parseVersion(value: string): number[] | null {
  const trimmed = value.trim().replace(/^v/i, "");
  if (trimmed.length === 0) return null;
  const parts = trimmed.split(".");
  const numbers: number[] = [];
  for (const part of parts) {
    // `03` is a real segment in this project's history, so parse decimally and
    // reject anything that is not purely numeric rather than guessing.
    if (!/^\d+$/.test(part)) return null;
    numbers.push(Number.parseInt(part, 10));
  }
  return numbers.length > 0 ? numbers : null;
}

/**
 * Compare two dotted numeric versions. Missing trailing segments count as 0,
 * so `0.15.17` and `0.15.17.0` are the same release.
 */
export function compareVersions(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index++) {
    const a = left[index] ?? 0;
    const b = right[index] ?? 0;
    if (a !== b) return a < b ? -1 : 1;
  }
  return 0;
}

/**
 * Classify the version recorded in a restored snapshot against the running one.
 *
 * An unparseable value on either side yields `unknown`: a result whose origin
 * cannot be established is exactly the case that must not be presented as
 * current.
 */
export function classifyResultVersion(
  recorded: string | null | undefined,
  current: string,
): ResultVersionRelation {
  if (typeof recorded !== "string") return "unknown";
  // An exact match settles it before any parsing. A build string is not always
  // a dotted number (a dev or CI build can carry a suffix), and a snapshot
  // written by the very build now reading it is the same run either way.
  if (recorded.trim().length > 0 && recorded.trim() === current.trim()) return "same";
  const recordedParts = parseVersion(recorded);
  const currentParts = parseVersion(current);
  if (!recordedParts || !currentParts) return "unknown";
  const order = compareVersions(recordedParts, currentParts);
  if (order === 0) return "same";
  return order < 0 ? "older" : "newer";
}

/**
 * What the restored result on screen was produced by. `null` when the results
 * came from a run in this session, or from a snapshot this build wrote itself.
 */
export interface RestoredResultProvenance {
  /** The recorded version, or null when the snapshot carried none. */
  version: string | null;
  relation: Exclude<ResultVersionRelation, "same">;
}

/**
 * The store value for a snapshot written by `version`: null when this build
 * wrote it, otherwise the origin to state on screen. Both restore paths (the
 * result file and the input-snapshot fallback) go through here so the two
 * cannot drift apart.
 */
export function provenanceFor(
  version: string | null | undefined,
  current: string,
): RestoredResultProvenance | null {
  const relation = classifyResultVersion(version, current);
  if (relation === "same") return null;
  return { version: version ?? null, relation };
}

const ACK_PREFIX = "kuma:mame:resultVersionAck:";

function ackKey(projectPath: string, version: string | null): string {
  return `${ACK_PREFIX}${projectPath}::${version ?? "unknown"}`;
}

/**
 * Has the operator already been told about this exact snapshot origin for this
 * project and chosen to keep it? The choice is recorded rather than assumed, so
 * the notice does not nag on every restart, and it is scoped per version so a
 * newer stale snapshot speaks up again.
 */
export function hasAcknowledgedResultVersion(
  projectPath: string,
  version: string | null,
): boolean {
  try {
    return localStorage.getItem(ackKey(projectPath, version)) !== null;
  } catch {
    // Storage unavailable: show the notice. Repeating a true statement is
    // better than hiding it.
    return false;
  }
}

/** Record that the operator chose to keep viewing a result from `version`. */
export function acknowledgeResultVersion(
  projectPath: string,
  version: string | null,
): void {
  try {
    localStorage.setItem(ackKey(projectPath, version), new Date().toISOString());
  } catch {
    // The dismissal still holds for this session; only its survival is lost.
  }
}
