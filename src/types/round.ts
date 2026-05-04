/**
 * TypeScript mirror of kuma_core/mame/activity/round.py Pydantic models.
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.3
 *
 * Keep in sync with:
 *   - kuma_core/mame/activity/round.py (Round, RoundStatus, RoundErrorInfo)
 *   - src/store/exportSlice.ts getWorkspaceSnapshot / restoreWorkspace
 */

import type { PlateMeta, ActivityRecord, MergedRow } from "./mame/activity"

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
}
