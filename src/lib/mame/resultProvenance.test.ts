/**
 * resultProvenance — classifying whose build wrote a restored result.
 *
 * The whole guard hangs on this comparison, so the cases that matter are the
 * ones a real project folder produces: this project's four-segment versions
 * with leading zeros (`0.15.17.03`), snapshots from before the field existed,
 * and a folder carried back from a newer machine.
 */

import { beforeEach, describe, expect, it } from "vitest";
import {
  acknowledgeResultVersion,
  classifyResultVersion,
  compareVersions,
  hasAcknowledgedResultVersion,
} from "./resultProvenance";

describe("classifyResultVersion", () => {
  it("calls an identical version the same build", () => {
    expect(classifyResultVersion("0.15.17.03", "0.15.17.03")).toBe("same");
  });

  it("treats a missing trailing segment as zero, not as a difference", () => {
    // 0.15.17 and 0.15.17.0 are one release; a notice here would be noise.
    expect(classifyResultVersion("0.15.17", "0.15.17.0")).toBe("same");
  });

  it("flags a snapshot from an earlier build", () => {
    expect(classifyResultVersion("0.15.9", "0.15.17.03")).toBe("older");
    expect(classifyResultVersion("0.15.17.02", "0.15.17.03")).toBe("older");
  });

  it("compares segments numerically, not as text", () => {
    // "0.15.9" > "0.15.17" as strings; the run order is the opposite.
    expect(classifyResultVersion("0.15.9", "0.15.17")).toBe("older");
    expect(classifyResultVersion("0.9.0", "0.15.0")).toBe("older");
  });

  it("reads a leading-zero segment decimally", () => {
    expect(classifyResultVersion("0.15.17.08", "0.15.17.09")).toBe("older");
    expect(classifyResultVersion("0.15.17.09", "0.15.17.08")).toBe("newer");
  });

  it("flags a snapshot from a later build", () => {
    expect(classifyResultVersion("0.16.0", "0.15.17.03")).toBe("newer");
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

describe("acknowledgement", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("is not acknowledged until the operator says so", () => {
    expect(hasAcknowledgedResultVersion("/p/one", "0.15.9")).toBe(false);
    acknowledgeResultVersion("/p/one", "0.15.9");
    expect(hasAcknowledgedResultVersion("/p/one", "0.15.9")).toBe(true);
  });

  it("is scoped per project", () => {
    acknowledgeResultVersion("/p/one", "0.15.9");
    expect(hasAcknowledgedResultVersion("/p/two", "0.15.9")).toBe(false);
  });

  it("speaks up again for a different producing version", () => {
    // Keeping one stale snapshot is not consent for the next one.
    acknowledgeResultVersion("/p/one", "0.15.9");
    expect(hasAcknowledgedResultVersion("/p/one", "0.15.14")).toBe(false);
  });

  it("keeps a versionless snapshot distinct from a versioned one", () => {
    acknowledgeResultVersion("/p/one", null);
    expect(hasAcknowledgedResultVersion("/p/one", null)).toBe(true);
    expect(hasAcknowledgedResultVersion("/p/one", "0.15.9")).toBe(false);
  });
});
