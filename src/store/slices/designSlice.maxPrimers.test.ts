/**
 * The design count is normalized to a positive integer and has no upper
 * bound: past one plate the export splits it into rounds, each on an Echo
 * source plate the operator picks.
 *
 * Exercised through the real store rather than `clampMaxPrimers` directly,
 * because the rule is only useful if every write path applies it.
 */

import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../appStore";
import { MAX_MUTATIONS_PER_RUN } from "../../lib/inputThresholds";

describe("setMaxPrimers", () => {
  afterEach(() => {
    useAppStore.setState({ maxPrimers: 95 });
  });

  it("keeps a count past two rounds", () => {
    useAppStore.getState().setMaxPrimers(500);
    expect(useAppStore.getState().maxPrimers).toBe(500);
    expect(MAX_MUTATIONS_PER_RUN).toBe(96);
  });

  it("falls back to one plate for a value that is not a finite number", () => {
    useAppStore.getState().setMaxPrimers(Number.NaN);
    expect(useAppStore.getState().maxPrimers).toBe(MAX_MUTATIONS_PER_RUN);
    useAppStore.getState().setMaxPrimers(Number.POSITIVE_INFINITY);
    expect(useAppStore.getState().maxPrimers).toBe(MAX_MUTATIONS_PER_RUN);
  });

  it("keeps the counts on both sides of the round boundary", () => {
    // 96 and 97 straddle the split into rounds, 192 and 193 the second, 288
    // and 289 the third. A fixture below 96 cannot tell a bound from none.
    for (const [n, want] of [[95, 95], [96, 96], [97, 97], [191, 191], [192, 192], [193, 193], [288, 288], [289, 289]]) {
      useAppStore.getState().setMaxPrimers(n);
      expect(useAppStore.getState().maxPrimers).toBe(want);
    }
  });

  it("raises a count below one", () => {
    useAppStore.getState().setMaxPrimers(0);
    expect(useAppStore.getState().maxPrimers).toBe(1);
  });

  it("leaves a count inside the range alone", () => {
    useAppStore.getState().setMaxPrimers(50);
    expect(useAppStore.getState().maxPrimers).toBe(50);
  });

  it("accepts exactly one full plate", () => {
    useAppStore.getState().setMaxPrimers(MAX_MUTATIONS_PER_RUN);
    expect(useAppStore.getState().maxPrimers).toBe(MAX_MUTATIONS_PER_RUN);
  });

  it("truncates a fractional count", () => {
    // The panel commits `parseFloat`, so "95.7" reaches the store as 95.7 and
    // a fractional count would flow on to the sidecar and to plate arithmetic.
    useAppStore.getState().setMaxPrimers(95.7);
    expect(useAppStore.getState().maxPrimers).toBe(95);
  });

  it("keeps the shipped default below the cap", () => {
    // 95 is the default the panel falls back to and the value every saved
    // fixture carries. A cap that moved it would rewrite existing projects.
    expect(useAppStore.getState().maxPrimers).toBe(95);
  });
});

// A CSV loaded at the default count used to freeze the selection at 95:
// raising the design count afterwards left it there and Run Design designed
// 95, so a sequential operator never reached a design past one plate.
describe("setMaxPrimers and a seeded EVOLVEpro selection", () => {
  const ranked = Array.from({ length: 145 }, (_, i) => ({
    variant: `V${i + 1}`,
    y_pred: 1 - i / 1000,
    aa_position: i + 2,
  }));
  const seeded = ranked.slice(0, 95).map((c) => c.variant);

  function seed(manual: boolean) {
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      maxPrimers: 95,
      evolveproRankedCandidates: ranked,
      evolveproSelectedVariants: [...seeded],
      evolveproSelectionManual: manual,
    });
  }

  afterEach(() => {
    useAppStore.setState({
      maxPrimers: 95,
      evolveproRankedCandidates: [],
      evolveproSelectedVariants: [],
      evolveproSelectionManual: false,
    });
  });

  it("grows the selection with the count, without a reload", () => {
    seed(false);
    useAppStore.getState().setMaxPrimers(120);
    expect(useAppStore.getState().evolveproSelectedVariants).toHaveLength(120);
  });

  it("shrinks the selection with the count", () => {
    seed(false);
    useAppStore.getState().setMaxPrimers(50);
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual(seeded.slice(0, 50));
  });

  it("leaves a hand-set selection alone", () => {
    seed(true);
    useAppStore.getState().setMaxPrimers(120);
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual(seeded);
  });

  it("still discards the designed primers when the count changes", () => {
    seed(false);
    useAppStore.setState({ designResults: [{ mutation: "V1" } as never] });
    useAppStore.getState().setMaxPrimers(120);
    expect(useAppStore.getState().designResults).toEqual([]);
  });
});
