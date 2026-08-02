/**
 * findStaleMamePaths: which restored MAME input paths no longer exist.
 *
 * The point of the helper is to let auto-detect run again. Auto-detect only
 * fills empty fields, so a dead absolute path left in the store blocks it.
 * Three behaviours are pinned: absent paths are reported, empty fields are not
 * (they are already auto-detect targets), and a path whose existence check
 * throws is kept rather than dropped, because a permission error or a slow
 * network drive is not evidence that the user file is gone.
 */

import { describe, expect, it, vi } from "vitest";
import { findStaleMamePaths, MAME_PATH_LABEL_KEYS } from "./stalePaths";

const ALL_PRESENT = {
  inputDir: "/proj/run",
  expectedPath: "/proj/expected.xlsx",
  referencePath: "/proj/ref.fasta",
  sampleMapPath: "/proj/samples.xlsx",
  customBarcodesPath: "/proj/barcodes.xlsx",
  sequencingSummaryPath: "/proj/sequencing_summary.txt",
};

describe("findStaleMamePaths", () => {
  it("reports only the paths that are gone", async () => {
    const gone = new Set(["/proj/run", "/proj/ref.fasta"]);
    const exists = vi.fn(async (p: string) => !gone.has(p));

    const stale = await findStaleMamePaths(ALL_PRESENT, exists);

    expect(stale).toEqual(["inputDir", "referencePath"]);
  });

  it("returns nothing when every path is present", async () => {
    const stale = await findStaleMamePaths(ALL_PRESENT, async () => true);
    expect(stale).toEqual([]);
  });

  it("skips empty fields without calling the filesystem", async () => {
    const exists = vi.fn(async () => false);

    const stale = await findStaleMamePaths(
      { inputDir: "", expectedPath: "", referencePath: "/proj/ref.fasta" },
      exists,
    );

    expect(stale).toEqual(["referencePath"]);
    expect(exists).toHaveBeenCalledTimes(1);
    expect(exists).toHaveBeenCalledWith("/proj/ref.fasta");
  });

  it("keeps a path whose existence check throws", async () => {
    const exists = vi.fn(async (p: string) => {
      if (p === "/proj/run") throw new Error("permission denied");
      return false;
    });

    const stale = await findStaleMamePaths(
      { inputDir: "/proj/run", expectedPath: "/proj/expected.xlsx" },
      exists,
    );

    // The unreadable one survives; only the confirmed-absent one is reported.
    expect(stale).toEqual(["expectedPath"]);
  });

  it("labels every field it can report", async () => {
    const stale = await findStaleMamePaths(ALL_PRESENT, async () => false);

    expect(stale).toHaveLength(6);
    for (const field of stale) {
      expect(MAME_PATH_LABEL_KEYS[field]).toMatch(/^autosaveHydration\.field/);
    }
  });
});
