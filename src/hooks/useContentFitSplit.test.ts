/**
 * The rule that replaced the fixed 34/66 on MAME step 2.2.
 *
 * The numbers in the first two cases are measured, not invented: at 1920x1080
 * the plate map needed 606 px and the breakdown 570 px inside a 925 px group,
 * and the old ratio gave the plate map 312 px, hiding 381 px of grid while the
 * panel below it had room left over (2026-08-05).
 */
import { describe, expect, it } from "vitest";
import { fitShare } from "./useContentFitSplit";

const MIN_FIRST = 18;
const MIN_SECOND = 30;

describe("fitShare", () => {
  it("gives the first panel exactly what it needs when both fit", () => {
    // 300 of 1000 wanted by the first, 400 by the second: everything fits, so
    // the first takes its 30% and the leftover goes to the second.
    expect(fitShare(300, 400, 1000, MIN_FIRST, MIN_SECOND)).toBeCloseTo(30, 5);
  });

  it("shares the shortfall in proportion to what each panel asked for", () => {
    // The measured step 2.2 case at 1920x1080.
    const share = fitShare(606, 570, 925, MIN_FIRST, MIN_SECOND);
    expect(share).toBeCloseTo((606 / 1176) * 100, 5);
    // Better than the ratio it replaced, which handed the larger appetite the
    // smaller share.
    expect(share).toBeGreaterThan(34);
  });

  it("never proposes a share either panel's minSize would refuse", () => {
    // A first panel that wants almost nothing, and one that wants everything.
    expect(fitShare(1, 900, 400, MIN_FIRST, MIN_SECOND)).toBe(MIN_FIRST);
    expect(fitShare(900, 1, 400, MIN_FIRST, MIN_SECOND)).toBe(100 - MIN_SECOND);
  });

  it("does not hand the whole group to a first panel that fits alone", () => {
    // Both fit and the first wants all of it: the second still keeps its floor.
    expect(fitShare(1000, 0, 1000, MIN_FIRST, MIN_SECOND)).toBe(100 - MIN_SECOND);
  });

  it("is stable when the two panels want the same height", () => {
    expect(fitShare(800, 800, 900, MIN_FIRST, MIN_SECOND)).toBeCloseTo(50, 5);
  });
});
