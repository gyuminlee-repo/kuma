/**
 * missingInputs: the list of inputs a restore could not recover.
 *
 * The comparison helper is the part worth pinning. Attaching a same-named but
 * different MinKNOW run is a real hazard, so a size mismatch must be caught.
 * Equally, missing evidence must not be treated as a mismatch: folders have no
 * size, and older snapshots recorded none.
 */

import { beforeEach, describe, expect, it } from "vitest";
import {
  formatSize,
  looksLikeSameTarget,
  useMissingInputs,
  type MissingInput,
} from "./missingInputs";

const RUN: MissingInput = {
  field: "inputDir",
  name: "20260212_1430_MN",
  size: 1_900_000_000,
};

describe("looksLikeSameTarget", () => {
  it("accepts a file whose size matches", () => {
    expect(looksLikeSameTarget(RUN, { name: "renamed", size: 1_900_000_000 })).toBe(true);
  });

  it("rejects a file whose size differs even when the name matches", () => {
    // The hazard: a different run of the same experiment, same folder naming.
    expect(looksLikeSameTarget(RUN, { name: "20260212_1430_MN", size: 12 })).toBe(false);
  });

  it("falls back to the name when either side has no size", () => {
    // Folders report no size, so the name is all there is to go on.
    expect(
      looksLikeSameTarget({ field: "inputDir", name: "run_a" }, { name: "run_a" }),
    ).toBe(true);
    expect(
      looksLikeSameTarget({ field: "inputDir", name: "run_a" }, { name: "run_b" }),
    ).toBe(false);
    // Recorded size but none available now: no evidence, so do not block.
    expect(looksLikeSameTarget(RUN, { name: "20260212_1430_MN" })).toBe(true);
  });
});

describe("formatSize", () => {
  it("renders human-readable sizes", () => {
    expect(formatSize(0)).toBe("0 B");
    expect(formatSize(1024)).toBe("1.0 KB");
    expect(formatSize(1_900_000_000)).toBe("1.8 GB");
  });

  it("returns null when there is nothing to show", () => {
    expect(formatSize(undefined)).toBeNull();
    expect(formatSize(Number.NaN)).toBeNull();
    expect(formatSize(-1)).toBeNull();
  });
});

describe("useMissingInputs", () => {
  beforeEach(() => {
    useMissingInputs.getState().clear();
  });

  it("replaces the list on each restore so a previous project leaves nothing behind", () => {
    useMissingInputs.getState().setMissing([RUN]);
    useMissingInputs.getState().setMissing([
      { field: "referencePath", name: "ref.fasta" },
    ]);

    expect(useMissingInputs.getState().items).toEqual([
      { field: "referencePath", name: "ref.fasta" },
    ]);
  });

  it("drops an entry once it is re-pointed", () => {
    useMissingInputs.getState().setMissing([
      RUN,
      { field: "referencePath", name: "ref.fasta" },
    ]);

    useMissingInputs.getState().resolve("inputDir");

    expect(useMissingInputs.getState().items).toEqual([
      { field: "referencePath", name: "ref.fasta" },
    ]);
  });
});
