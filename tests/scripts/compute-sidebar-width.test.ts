/**
 * scripts/compute-sidebar-width.mjs: the width heuristic behind
 * src/lib/sidebar-default-width.ts.
 *
 * This file replaces scripts/compute-sidebar-width.test.mjs, which no runner
 * collected: vitest.config.ts includes only `src/**\/*.test.{ts,tsx}` and
 * `tests/**\/*.test.ts`, there is no `node --test` npm script, and no workflow
 * ran one. Its "longer label produces larger width" case also compared a label
 * that computes to 147 px and is then clamped to exactly 180 px against the
 * 180 px clamp constant itself, so it passed for any broken implementation
 * below the clamp.
 *
 * Every case below either lands strictly above the clamp, where the
 * per-character arithmetic is what is being measured, or pins the clamp
 * deliberately.
 *
 * Latin characters count 7.3 px at fontSize 14 (scale 1) and padding is 44 px,
 * so the expected values are ceil(chars * 7.3 * scale + 44).
 *
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import { computeMaxLabelWidth } from "../../scripts/compute-sidebar-width.mjs";

/**
 * Lengths are deliberately not multiples of 10: the width is accumulated one
 * character at a time, so a label whose ideal total lands exactly on an integer
 * (40 chars gives 292.0) can drift past it and take the ceil up by 1 px. These
 * lengths leave the expected value off any such boundary.
 */
/** 21 latin characters: ceil(21 * 7.3 + 44) = ceil(197.3) = 198, above the clamp. */
const LABEL_21 = "Pool filters and runs";
/** 41 latin characters: ceil(41 * 7.3 + 44) = ceil(343.3) = 344. */
const LABEL_41 = "Pool filters and runs with extra padding!";
/** 5 latin characters: ceil(5 * 7.3 + 44) = 81, below the clamp. */
const LABEL_5 = "short";

describe("computeMaxLabelWidth", () => {
  it("returns the per-character estimate plus padding above the clamp", () => {
    expect(LABEL_21).toHaveLength(21);
    expect(LABEL_41).toHaveLength(41);
    expect(computeMaxLabelWidth([LABEL_21], { fontSize: 14, padding: 44 })).toBe(198);
    expect(computeMaxLabelWidth([LABEL_41], { fontSize: 14, padding: 44 })).toBe(344);
  });

  it("takes the widest label and scales with fontSize", () => {
    // The maximum wins regardless of order, and doubling fontSize doubles the
    // character contribution while leaving the padding term alone:
    // ceil(41 * 7.3 * 2 + 44) = ceil(642.6) = 643.
    expect(computeMaxLabelWidth([LABEL_21, LABEL_41], { fontSize: 14, padding: 44 })).toBe(344);
    expect(computeMaxLabelWidth([LABEL_41, LABEL_21], { fontSize: 14, padding: 44 })).toBe(344);
    expect(computeMaxLabelWidth([LABEL_41], { fontSize: 28, padding: 44 })).toBe(643);
  });

  it("clamps labels whose estimate falls below 180 px", () => {
    // 81 and 51 unclamped; both are reported as the 180 px floor.
    expect(computeMaxLabelWidth([LABEL_5], { fontSize: 14, padding: 44 })).toBe(180);
    expect(computeMaxLabelWidth(["a"], { fontSize: 14, padding: 44 })).toBe(180);
  });

  it("returns the fallback for an empty label list", () => {
    expect(computeMaxLabelWidth([], { fontSize: 14, padding: 44, fallback: 240 })).toBe(240);
  });
});
