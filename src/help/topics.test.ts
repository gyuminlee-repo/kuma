import { describe, it, expect } from "vitest";
import { HELP_GROUPS, ALL_TOPIC_IDS, STEP_TO_TOPIC, topicForStep } from "./topics";
import { listLoadedTopics, getTopicBody } from "./content";
import { KURO_STEP_INDEX } from "../components/steps/constants";
import { MAME_SUBSTEP_ORDER } from "../store/mame/slices/mameSubSteps";

/**
 * Markdown links whose target ends in the markdown extension, resolved the way
 * HelpMarkdown resolves them: the last path segment without the extension.
 * Every link target is collected first, so a target carrying a directory is
 * checked rather than skipped by a narrow pattern.
 */
function brokenReferences(id: string, body: string, known: readonly string[]): string[] {
  const ext = "." + "md";
  const broken: string[] = [];
  for (const m of body.matchAll(/\]\(([^)\s]+)\)/g)) {
    const target = m[1];
    if (!target.endsWith(ext)) continue;
    const stem = (target.split("/").pop() ?? "").slice(0, -ext.length);
    if (!known.includes(stem)) broken.push(`${id} -> ${target}`);
  }
  return broken;
}

describe("help topics", () => {
  it("lists every topic exactly once across the groups", () => {
    const flat = HELP_GROUPS.flatMap((g) => g.topics);
    expect(new Set(flat).size).toBe(flat.length);
    expect([...flat].sort()).toEqual([...ALL_TOPIC_IDS].sort());
  });

  it("names exactly the topics that were loaded, in both locales", () => {
    expect([...ALL_TOPIC_IDS].sort()).toEqual(listLoadedTopics("ko").sort());
    expect([...ALL_TOPIC_IDS].sort()).toEqual(listLoadedTopics("en").sort());
  });

  it("maps every step id the two stores declare to a real topic", () => {
    const storeSteps = [
      ...Object.keys(KURO_STEP_INDEX),
      ...Object.values(MAME_SUBSTEP_ORDER).flat(),
    ];
    expect(storeSteps.length).toBeGreaterThan(0);
    for (const step of storeSteps) {
      expect(Object.keys(STEP_TO_TOPIC)).toContain(step);
      expect(ALL_TOPIC_IDS).toContain(topicForStep(step));
    }
    for (const topic of Object.values(STEP_TO_TOPIC)) {
      expect(ALL_TOPIC_IDS).toContain(topic);
    }
  });

  it("opens an index for an unmapped, null or undefined step", () => {
    expect(topicForStep("no.such.step")).toBe("mame-index");
    expect(topicForStep("design.unknown")).toBe("kuro-index");
    expect(topicForStep(null)).toBe("mame-index");
    expect(topicForStep(undefined)).toBe("mame-index");
    expect(topicForStep("")).toBe("mame-index");
  });

  it("has no cross-reference pointing at a topic that does not exist", () => {
    const broken: string[] = [];
    for (const loc of ["ko", "en"] as const) {
      for (const id of ALL_TOPIC_IDS) {
        broken.push(...brokenReferences(`${loc}/${id}`, getTopicBody(id, loc).body, ALL_TOPIC_IDS));
      }
    }
    expect(broken).toEqual([]);
  });

  it("catches an injected link to a missing topic, with or without a directory", () => {
    const ext = "." + "md";
    const body = `[a](mame-02-review${ext}) [b](gone-topic${ext}) [c](../mame/also-gone${ext}) [d](https://example.org)`;
    expect(brokenReferences("probe", body, ALL_TOPIC_IDS)).toEqual([
      `probe -> gone-topic${ext}`,
      `probe -> ../mame/also-gone${ext}`,
    ]);
  });
});
