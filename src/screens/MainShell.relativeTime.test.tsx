import i18next from "i18next";
import { describe, expect, it } from "vitest";
import { formatRelativeTime } from "./MainShell";

// src/test-setup.ts already ran initI18n("en"), so this is the real interpolator
// over the real en.json. That matters: a hand-written `t` stub returns whatever
// it is told to and would have passed against the broken string this test covers.
const t = (key: string, opts?: Record<string, string | number>) => i18next.t(key, opts);

const isoAgo = (ms: number) => new Date(Date.now() - ms).toISOString();

describe("formatRelativeTime", () => {
  it("interpolates the days branch instead of leaving the token on screen", () => {
    const out = formatRelativeTime(isoAgo(3 * 24 * 60 * 60_000 + 60_000), t);
    // The defect was daysAgo declaring {{count}} while the call passes { n }:
    // i18next found no match and every locale rendered the literal token.
    expect(out).not.toContain("{{");
    expect(out).toBe("3 day(s) ago");
  });

  it("says the time is unknown when the timestamp cannot be parsed", () => {
    for (const bad of ["not-a-date", "", "2026-13-45T99:99:99Z"]) {
      const out = formatRelativeTime(bad, t);
      // Every comparison against NaN is false, so without the guard control
      // reached the days branch and printed "NaN day(s) ago".
      expect(out).not.toContain("NaN");
      expect(out).toBe("at an unknown time");
    }
  });

  it("keeps the minutes, hours and just-now branches", () => {
    expect(formatRelativeTime(isoAgo(5_000), t)).toBe("just now");
    expect(formatRelativeTime(isoAgo(7 * 60_000), t)).toBe("7 min ago");
    expect(formatRelativeTime(isoAgo(3 * 60 * 60_000), t)).toBe("3 hr ago");
  });
});
