/**
 * kuroResultReset.test.ts, the invalidation patch has to cover the whole
 * result block, and its rescue-stats literal has to stay pinned to the slice.
 *
 * A user autosave carried designResults 0 / totalCount 0 while rescuedMutations
 * still held 6 entries. That combination is only reachable through this patch,
 * because it was the one writer that cleared the table and left the rescue list
 * standing. The gap made the fingerprint useful once and misleading forever, so
 * the fields are pinned here instead.
 */

import { describe, expect, it } from "vitest";
import { buildKuroResultResetPatch } from "./kuroResultReset";
import { EMPTY_RESCUE_STATS } from "@/store/slices/designSlice.helpers";

describe("buildKuroResultResetPatch", () => {
  it("clears the rescue list and the rescue counters with the results", () => {
    const patch = buildKuroResultResetPatch();
    expect(patch.designResults).toEqual([]);
    expect(patch.rescuedMutations).toEqual([]);
    expect(patch.rescuedMutationDetails).toEqual([]);
    // The literal in kuroResultReset.ts exists to keep that module free of
    // store imports; this is what stops the two from drifting apart.
    expect(patch.rescueStats).toEqual(EMPTY_RESCUE_STATS);
  });

  it("covers every field the autosave result block restores", () => {
    // Source of truth: kuroSnapshot.buildKuroSnapshot `results` block. Anything
    // it saves and this patch misses comes back on restore next to an empty
    // table. showBenchmark/poolVariants/alternativesCache/benchmarkResults are
    // deliberately excluded: they outlive a single design run.
    const restored = [
      "designResults",
      "successCount",
      "totalCount",
      "failedMutations",
      "plateMappings",
      "dedupInfo",
      "manuallySwapped",
      "customCandidates",
      "rescuedMutationDetails",
      "rescuedMutations",
    ];
    const patch = buildKuroResultResetPatch();
    for (const field of restored) {
      expect(Object.keys(patch)).toContain(field);
    }
  });
});
