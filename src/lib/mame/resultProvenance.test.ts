/**
 * resultProvenance — classifying whose build wrote a restored result.
 *
 * The whole guard hangs on this comparison, so the cases that matter are the
 * ones a real project folder produces: this project's four-segment versions
 * with leading zeros (`0.15.17.03`), snapshots from before the field existed,
 * and a folder carried back from a newer machine.
 */

import { describe, expect, it } from "vitest";
import { classifyResultVersion, compareVersions, provenanceFor } from "./resultProvenance";
import { RESULT_CONTRACT } from "./resultContract";

describe("classifyResultVersion", () => {
  it("takes the stamped contract as authoritative", () => {
    // The version is only a fallback: a snapshot that says which contract it
    // was produced at is judged by that, whatever release wrote it.
    expect(classifyResultVersion("0.15.9", "9.9.9", RESULT_CONTRACT)).toBe("same");
    expect(classifyResultVersion("9.9.9", "0.15.9", RESULT_CONTRACT - 1)).toBe("older");
    expect(classifyResultVersion("0.15.9", "0.15.9", RESULT_CONTRACT + 1)).toBe("newer");
  });

  it("ignores releases that changed nothing about results", () => {
    // This is the whole point of the contract: v0.15.11 (panel heights) and
    // v0.15.12 (the Janus step split) produce the same result as v0.15.10, so
    // a project saved by any of them restores untouched.
    expect(classifyResultVersion("0.15.11", "0.15.12")).toBe("same");
    expect(classifyResultVersion("0.15.12", "0.15.11")).toBe("same");
    expect(classifyResultVersion("0.15.17", "0.15.17.02")).toBe("same");
  });

  it("flags only a release that crossed a result-affecting change", () => {
    expect(classifyResultVersion("0.15.12", "0.15.13")).toBe("older");
    expect(classifyResultVersion("0.15.17.02", "0.15.17.03")).toBe("older");
    expect(classifyResultVersion("0.15.19", "0.15.18")).toBe("newer");
  });

  it("calls an identical version the same build", () => {
    expect(classifyResultVersion("0.15.17.03", "0.15.17.03")).toBe("same");
  });

  it("treats a missing trailing segment as zero, not as a difference", () => {
    // 0.15.17 and 0.15.17.0 are one release; a notice here would be noise.
    expect(classifyResultVersion("0.15.17", "0.15.17.0")).toBe("same");
  });

  it("flags a snapshot from a build that predates a result change", () => {
    expect(classifyResultVersion("0.15.9", "0.15.17.03")).toBe("older");
    expect(classifyResultVersion("0.15.17.02", "0.15.17.03")).toBe("older");
  });

  it("compares segments numerically, not as text", () => {
    // "0.15.9" > "0.15.17" as strings; the run order is the opposite, and
    // 0.15.9 predates four result changes that 0.15.17 has.
    expect(classifyResultVersion("0.15.9", "0.15.17")).toBe("older");
  });

  it("calls two releases from before every result change the same", () => {
    // 0.9.0 and 0.15.0 are far apart as releases and identical as contracts:
    // nothing about a result changed between them, so there is nothing to
    // re-run for.
    expect(classifyResultVersion("0.9.0", "0.15.0")).toBe("same");
  });

  it("reads a leading-zero segment decimally", () => {
    // Both sit after v0.15.17.03 and before v0.15.19, so as contracts they are
    // the same; the decimal parse itself is pinned in resultContract.test.ts.
    expect(classifyResultVersion("0.15.17.08", "0.15.17.09")).toBe("same");
    expect(classifyResultVersion("0.15.17.02", "0.15.17.03")).toBe("older");
  });

  it("flags a snapshot from a later build", () => {
    // 0.16.0 is past v0.15.19, the newest recorded change, so against a build
    // that stops at v0.15.17.03 it is a contract ahead.
    expect(classifyResultVersion("0.16.0", "0.15.17.03")).toBe("newer");
  });

  it("treats two pre-history releases as the same contract", () => {
    // Both predate every recorded change, so neither would score differently.
    expect(classifyResultVersion("0.14.0", "0.15.9")).toBe("same");
  });

  it("refuses to trust a snapshot with no version", () => {
    expect(classifyResultVersion(undefined, "0.15.17.03")).toBe("unknown");
    expect(classifyResultVersion(null, "0.15.17.03")).toBe("unknown");
    expect(classifyResultVersion("", "0.15.17.03")).toBe("unknown");
  });

  it("refuses to guess at an unparseable version", () => {
    expect(classifyResultVersion("0.15.x", "0.15.17.03")).toBe("unknown");
    expect(classifyResultVersion("nightly", "0.15.17.03")).toBe("unknown");
  });

  it("tolerates a leading v on either side", () => {
    expect(classifyResultVersion("v0.15.17.03", "0.15.17.03")).toBe("same");
  });

  it("calls a non-numeric build string the same when it matches exactly", () => {
    // Dev and CI builds carry suffixes; a snapshot written by the build now
    // reading it must not raise a notice just because it cannot be parsed.
    expect(classifyResultVersion("0.0.0-test", "0.0.0-test")).toBe("same");
    expect(classifyResultVersion("0.0.0-test", "0.15.17.03")).toBe("unknown");
  });
});

describe("compareVersions", () => {
  it("orders by the first differing segment", () => {
    expect(compareVersions([0, 15, 9], [0, 15, 17])).toBe(-1);
    expect(compareVersions([1, 0], [0, 99])).toBe(1);
    expect(compareVersions([0, 15], [0, 15, 0])).toBe(0);
  });
});

describe("provenanceFor", () => {
  it("returns null when the contracts match, so the run restores untouched", () => {
    expect(provenanceFor("0.15.11", "0.15.12")).toBeNull();
    expect(provenanceFor("0.15.9", "9.9.9", RESULT_CONTRACT)).toBeNull();
  });

  it("carries the reasons a re-run is being demanded", () => {
    const provenance = provenanceFor("0.15.9", "0.15.19");
    expect(provenance?.relation).toBe("older");
    expect(provenance?.contract).toBe(0);
    expect(provenance?.changes.map((change) => change.revision)).toEqual([1, 2, 3, 4, 5]);
  });

  it("lists nothing it cannot know for a newer or unidentifiable origin", () => {
    const newer = provenanceFor("9.9.9", "0.15.19", RESULT_CONTRACT + 1);
    expect(newer?.relation).toBe("newer");
    expect(newer?.changes).toEqual([]);
    expect(provenanceFor("nightly", "0.15.19")?.relation).toBe("unknown");
    expect(provenanceFor("nightly", "0.15.19")?.changes).toEqual([]);
  });
});
