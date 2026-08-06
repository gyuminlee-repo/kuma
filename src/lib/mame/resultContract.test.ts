/**
 * resultContract — the table that decides whether a saved run is obsolete.
 *
 * Two things must stay true or the whole guard misfires: the table has to be
 * ordered and self-consistent, and every entry needs the copy that justifies
 * the re-run it will demand. The second half is checked against the shipped
 * English catalogue, because a revision whose reason renders as a raw i18n key
 * is a re-run demand with no argument behind it.
 */

import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import {
  RESULT_CONTRACT,
  RESULT_CONTRACT_REVISIONS,
  changesSince,
  compareVersionParts,
  parseVersionParts,
  revisionForVersion,
} from "./resultContract";

describe("RESULT_CONTRACT_REVISIONS", () => {
  it("is numbered from 1 with no gaps", () => {
    expect(RESULT_CONTRACT_REVISIONS.map((r) => r.revision)).toEqual(
      RESULT_CONTRACT_REVISIONS.map((_, index) => index + 1),
    );
  });

  it("is ordered by the release each revision shipped in", () => {
    for (let index = 1; index < RESULT_CONTRACT_REVISIONS.length; index++) {
      const previous = parseVersionParts(RESULT_CONTRACT_REVISIONS[index - 1]!.since)!;
      const current = parseVersionParts(RESULT_CONTRACT_REVISIONS[index]!.since)!;
      expect(compareVersionParts(previous, current)).toBeLessThan(0);
    }
  });

  it("carries a parseable release for every entry", () => {
    for (const entry of RESULT_CONTRACT_REVISIONS) {
      expect(parseVersionParts(entry.since)).not.toBeNull();
    }
  });

  it("agrees with RESULT_CONTRACT", () => {
    // Bumping the table without bumping the constant would leave this build
    // claiming to produce an older contract than it does.
    expect(RESULT_CONTRACT).toBe(
      RESULT_CONTRACT_REVISIONS[RESULT_CONTRACT_REVISIONS.length - 1]!.revision,
    );
  });

  it("has shipped copy for every revision", () => {
    const catalogue = (en as { mame: { restoredResult: { change: Record<string, string> } } })
      .mame.restoredResult.change;
    for (const entry of RESULT_CONTRACT_REVISIONS) {
      expect(catalogue[entry.key], `missing copy for revision ${entry.revision}`).toBeTruthy();
    }
  });

  it("has no orphaned copy left behind by a removed revision", () => {
    const catalogue = (en as { mame: { restoredResult: { change: Record<string, string> } } })
      .mame.restoredResult.change;
    const keys = new Set(RESULT_CONTRACT_REVISIONS.map((entry) => entry.key));
    for (const key of Object.keys(catalogue)) {
      expect(keys.has(key), `copy for unknown revision key ${key}`).toBe(true);
    }
  });
});

describe("revisionForVersion", () => {
  it("maps a release older than every entry to revision 0", () => {
    expect(revisionForVersion("0.15.9")).toBe(0);
    expect(revisionForVersion("0.14.0")).toBe(0);
  });

  it("maps the release an entry shipped in to that revision", () => {
    expect(revisionForVersion("0.15.10")).toBe(1);
    expect(revisionForVersion("0.15.13")).toBe(2);
    expect(revisionForVersion("0.15.19")).toBe(5);
  });

  it("keeps a release between two entries at the earlier revision", () => {
    // The point of the whole table: 0.15.11 and 0.15.12 changed panels and
    // steps, not results, so they must not read as a newer contract.
    expect(revisionForVersion("0.15.11")).toBe(1);
    expect(revisionForVersion("0.15.12")).toBe(1);
    expect(revisionForVersion("0.15.18")).toBe(4);
  });

  it("reads a leading-zero segment decimally", () => {
    expect(revisionForVersion("0.15.17.02")).toBe(3);
    expect(revisionForVersion("0.15.17.03")).toBe(4);
  });

  it("refuses to guess at an unparseable version", () => {
    expect(revisionForVersion("nightly")).toBeNull();
    expect(revisionForVersion("")).toBeNull();
    expect(revisionForVersion(undefined)).toBeNull();
  });
});

describe("changesSince", () => {
  it("lists only what came after the given revision", () => {
    expect(changesSince(RESULT_CONTRACT)).toEqual([]);
    expect(changesSince(4).map((entry) => entry.revision)).toEqual([5]);
    expect(changesSince(0)).toHaveLength(RESULT_CONTRACT_REVISIONS.length);
  });
});
