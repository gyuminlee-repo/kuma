import type {
  ReplicateResult,
  SelectionOverride,
  VerdictClass,
  WellEntry,
} from "@/types/mame/models";

/** Longest note the sidecar keeps (`MAX_NOTE_LENGTH` in select/manual_override.py). */
export const MAX_OVERRIDE_NOTE_LENGTH = 500;

/**
 * The overrides in force, read off the replicates themselves. The replicates are
 * already what the autosave and the result file persist, and the sidecar rebuilds
 * its own state from them, so the list is never stored a second time where it
 * could disagree with them.
 */
export function overridesFromReplicates(
  replicates: readonly ReplicateResult[],
): SelectionOverride[] {
  const out: SelectionOverride[] = [];
  for (const rr of replicates) {
    if (rr.manual && rr.selected_plate) {
      out.push({
        mutant_id: rr.mutant_id,
        plate: rr.selected_plate,
        note: rr.manual.note,
      });
    }
  }
  return out;
}

/** The verdict class of the copy a replicate currently selects, or null when it selects none. */
export function selectedVerdict(rr: ReplicateResult): VerdictClass | null {
  if (rr.failed || !rr.selected_plate) return null;
  return rr.plate_verdicts[rr.selected_plate]?.verdict ?? null;
}

/**
 * A well needs a decision when nothing usable is selected: no copy, a failed
 * pick, a fallback pick, or a selected copy that is not PASS. PASS is the only
 * class the pick list and the instrument export include by default, so anything
 * else is a well that leaves those files empty. A manually confirmed well is
 * settled by definition.
 */
export function needsConfirmation(rr: ReplicateResult): boolean {
  if (rr.manual) return false;
  return rr.is_fallback || selectedVerdict(rr) !== "PASS";
}

/** The well a mutant sits in, from the plate data (null before it has loaded). */
export function wellOfMutant(
  wells: readonly WellEntry[],
  mutantId: string,
): string | null {
  return wells.find((w) => w.mutant_id === mutantId)?.well ?? null;
}
