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
import { RESULT_CONTRACT, RESULT_CONTRACT_REVISIONS } from "./resultContract";

/**
 * The release the newest revision shipped in. Every case below is judged against
 * `RESULT_CONTRACT`, which is what this build produces, so the version passed as
 * `current` only drives the exact-string shortcut. Deriving it from the table
 * keeps these cases correct when a revision is added.
 */
const NEWEST_SINCE = RESULT_CONTRACT_REVISIONS[RESULT_CONTRACT_REVISIONS.length - 1]!.since;

describe("classifyResultVersion", () => {
  it("takes the stamped contract as authoritative", () => {
    // The version is only a fallback: a snapshot that says which contract it
    // was produced at is judged by that, whatever release wrote it.
    expect(classifyResultVersion("0.15.9", "9.9.9", RESULT_CONTRACT)).toBe("same");
    expect(classifyResultVersion("9.9.9", "0.15.9", RESULT_CONTRACT - 1)).toBe("older");
    expect(classifyResultVersion("0.15.9", "0.15.9", RESULT_CONTRACT + 1)).toBe("newer");
  });

  it("measures an unstamped snapshot against this build, not against `current`", () => {
    // The target is RESULT_CONTRACT: what this build's analyze produces. It is
    // NOT derived from `current`, because a revision is added as part of
    // changing analyze behaviour and therefore lands before the release named
    // in its `since`. In that window a version-derived target sits one behind,
    // and every result at the older revision reads as "same" and restores as
    // current. 0.16.24 is such a version while revision 7's `since` is 0.16.25:
    // a version-derived target would call this pair "same" and hand the older
    // run back as this build's answer.
    expect(classifyResultVersion("0.16.24", "0.16.24.1")).toBe("older");
    expect(classifyResultVersion("0.15.12", NEWEST_SINCE)).toBe("older");
    expect(classifyResultVersion("0.15.17.02", "0.15.18")).toBe("older");
    expect(classifyResultVersion(NEWEST_SINCE, "9.9.9")).toBe("same");
  });

  it("ignores releases that changed nothing about results", () => {
    // This is the whole point of the contract: v0.15.11 (panel heights) and
    // v0.15.12 (the Janus step split) produce the same result as v0.15.10, so
    // the three are not told apart, whichever way the comparison falls.
    expect(classifyResultVersion("0.15.11", NEWEST_SINCE)).toBe(
      classifyResultVersion("0.15.12", NEWEST_SINCE),
    );
    expect(classifyResultVersion("0.15.17", NEWEST_SINCE)).toBe(
      classifyResultVersion("0.15.17.02", NEWEST_SINCE),
    );
  });

  it("calls an identical version the same build", () => {
    expect(classifyResultVersion("0.15.17.03", "0.15.17.03")).toBe("same");
  });

  it("treats a missing trailing segment as zero, not as a difference", () => {
    // 0.16.25 and 0.16.25.0 are one release; a notice here would be noise.
    expect(classifyResultVersion(`${NEWEST_SINCE}.0`, NEWEST_SINCE)).toBe("same");
  });

  it("flags a snapshot from a build that predates a result change", () => {
    expect(classifyResultVersion("0.15.9", NEWEST_SINCE)).toBe("older");
    expect(classifyResultVersion("0.15.17.02", NEWEST_SINCE)).toBe("older");
  });

  it("compares segments numerically, not as text", () => {
    // "0.15.9" > "0.15.17" as strings; the run order is the opposite, and
    // 0.15.9 predates result changes that 0.15.17 has.
    expect(classifyResultVersion("0.15.9", NEWEST_SINCE)).toBe("older");
  });

  it("calls two releases from before every result change the same", () => {
    // 0.9.0 and 0.15.0 are far apart as releases and identical as contracts:
    // nothing about a result changed between them, so they answer alike.
    expect(classifyResultVersion("0.9.0", NEWEST_SINCE)).toBe(
      classifyResultVersion("0.15.0", NEWEST_SINCE),
    );
  });

  it("reads a leading-zero segment decimally", () => {
    // Both sit after v0.15.17.03 and before v0.15.19, so as contracts they are
    // the same; the decimal parse itself is pinned in resultContract.test.ts.
    expect(classifyResultVersion("0.15.17.08", NEWEST_SINCE)).toBe(
      classifyResultVersion("0.15.17.09", NEWEST_SINCE),
    );
  });

  it("cannot read an unstamped snapshot as newer, because the table stops here", () => {
    // The release table only lists revisions this build implements, so no
    // version string maps above RESULT_CONTRACT. A newer origin is knowable
    // only from a stamped contract, which the first case covers. Builds have
    // stamped `result_contract` since v0.15.21, so unstamped-and-newer is not
    // a combination a real project folder carries.
    expect(classifyResultVersion("99.0.0", NEWEST_SINCE)).toBe("same");
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
    expect(classifyResultVersion(`v${NEWEST_SINCE}`, NEWEST_SINCE)).toBe("same");
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
    expect(provenanceFor(NEWEST_SINCE, "0.16.99")).toBeNull();
    expect(provenanceFor("0.15.9", "9.9.9", RESULT_CONTRACT)).toBeNull();
  });

  it("carries the reasons a re-run is being demanded", () => {
    // A pre-history snapshot is owed every recorded change, because every one
    // of them happened after it was written.
    const provenance = provenanceFor("0.15.9", NEWEST_SINCE);
    expect(provenance?.relation).toBe("older");
    expect(provenance?.contract).toBe(0);
    expect(provenance?.changes.map((change) => change.revision)).toEqual(
      RESULT_CONTRACT_REVISIONS.map((change) => change.revision),
    );
  });

  it("lists nothing it cannot know for a newer or unidentifiable origin", () => {
    const newer = provenanceFor("9.9.9", "0.15.19", RESULT_CONTRACT + 1);
    expect(newer?.relation).toBe("newer");
    expect(newer?.changes).toEqual([]);
    expect(provenanceFor("nightly", "0.15.19")?.relation).toBe("unknown");
    expect(provenanceFor("nightly", "0.15.19")?.changes).toEqual([]);
  });
});
