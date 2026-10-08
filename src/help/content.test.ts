import { describe, it, expect } from "vitest";
import { getTopicBody, listLoadedTopics } from "./content";

describe("help content", () => {
  it("loads every Korean and English topic as non-empty text", () => {
    for (const loc of ["ko", "en"] as const) {
      const ids = listLoadedTopics(loc);
      expect(ids.length).toBe(13);
      for (const id of ids) {
        expect(getTopicBody(id, loc).body.length).toBeGreaterThan(0);
      }
    }
  });

  it("serves the requested locale without a fallback flag", () => {
    const r = getTopicBody("mame-01-setup", "ko");
    expect(r.usedLocale).toBe("ko");
    expect(r.fellBack).toBe(false);
  });

  it("falls back to English and says so", () => {
    const r = getTopicBody("mame-01-setup", "ja");
    expect(r.usedLocale).toBe("en");
    expect(r.fellBack).toBe(true);
    expect(r.body).toBe(getTopicBody("mame-01-setup", "en").body);
  });

  it("reads a region-tagged locale as its base language", () => {
    for (const tag of ["ko-KR", "KO", "ko_KR"]) {
      const r = getTopicBody("mame-01-setup", tag);
      expect(r.usedLocale).toBe("ko");
      expect(r.fellBack).toBe(false);
    }
    const us = getTopicBody("mame-01-setup", "en-US");
    expect(us.usedLocale).toBe("en");
    expect(us.fellBack).toBe(false);
    const tw = getTopicBody("mame-01-setup", "zh-TW");
    expect(tw.usedLocale).toBe("en");
    expect(tw.fellBack).toBe(true);
  });

  it("reports a missing topic rather than returning empty text silently", () => {
    const r = getTopicBody("no-such-topic", "ko");
    expect(r.usedLocale).toBeNull();
    expect(r.body).toBe("");
    expect(r.fellBack).toBe(false);
  });

  it("carries the same topic set in both locales", () => {
    expect(listLoadedTopics("ko").sort()).toEqual(listLoadedTopics("en").sort());
  });
});
