/**
 * TypeScript mirror of kuma_core/mame/activity/round.py Pydantic models.
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.3
 *
 * Keep in sync with:
 *   - kuma_core/mame/activity/round.py (Round, RoundStatus, RoundErrorInfo)
 *   - src/store/exportSlice.ts getWorkspaceSnapshot / restoreWorkspace
 */

import type { PlateMeta, ActivityRecord, MergedRow } from "./mame/activity"
import type { ClassifyRoundResult, RoundFileEntry } from "./mame/strategy"

export type RoundStatus =
  | "design"
  | "ordered"
  | "ngs_done"
  | "activity_linked"
  | "exported"
  | "combinatorial"
  | "closed"
  | "error"

export interface RoundErrorInfo {
  stage: "upload" | "merge" | "export" | "handoff"
  message: string
  occurred_at: string
}

/** A file one round produced, with the moment it was written. */
export interface RoundArtifact {
  path: string
  produced_at: string
}

/**
 * An advisory answer, kept with the inputs that produced it.
 *
 * The answer alone cannot be re-examined later: it is a statement about one
 * ordered set of round files at one moment. Storing the files and the time
 * alongside it is what lets a restored answer say what it was about, and
 * `input_signature` is what lets the screen tell whether the list in front of
 * the operator is still that same list.
 */
export interface RoundAdvisoryRecord {
  /** The sidecar response verbatim, decision or not_assessable. */
  result: ClassifyRoundResult
  /** The files it was computed from, with the round numbers they were sent as. */
  inputs: RoundFileEntry[]
  /** ISO timestamp of when the answer came back. */
  decided_at: string
  /**
   * Identity of `inputs` including their contents, from roundFilesSignature
   * (lib/round/roundArtifacts.ts): each entry carries the moment the app wrote
   * that file, so rebuilding a round over the same path no longer looks like
   * the list the answer was computed from.
   */
  input_signature: string
}

export interface Round {
  id: string
  n: number
  created_at: string
  status: RoundStatus
  error_info: RoundErrorInfo | null
  plate_meta: PlateMeta
  design: Record<string, unknown>
  genotype: Record<string, unknown>
  activity: { records: ActivityRecord[]; plate_meta: PlateMeta } | null
  merged_table: MergedRow[]
  /**
   * The EVOLVEpro input step 4.1 built for this round, which step 4.2 reads
   * back as one entry of the round series (lib/round/roundArtifacts.ts).
   *
   * Optional because rounds restored from a snapshot written before this field
   * existed simply do not have it. Absent reads as "this round produced
   * nothing", which is the same answer those projects give today, so no
   * snapshot schema bump is warranted.
   */
  evolvepro_input?: RoundArtifact | null
  /**
   * The last advisory answer computed while this round was active.
   *
   * Optional for the same reason as `evolvepro_input`: absent on rounds
   * restored from an older snapshot, and absent means no advisory has been run,
   * which is what those projects report today.
   */
  advisory?: RoundAdvisoryRecord | null
}
