/**
 * The design count is bounded to one plate.
 *
 * Exercised through the real store rather than `clampMaxPrimers` directly:
 * the bound is only useful if every write path applies it, and testing the
 * helper alone would still pass with the store calling `Math.max(1, n)`.
 */

import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../appStore";
import { MAX_MUTATIONS_PER_RUN } from "../../lib/inputThresholds";

describe("setMaxPrimers", () => {
  afterEach(() => {
    useAppStore.setState({ maxPrimers: 95 });
  });

  it("caps a count above one plate", () => {
    useAppStore.getState().setMaxPrimers(500);
    expect(useAppStore.getState().maxPrimers).toBe(MAX_MUTATIONS_PER_RUN);
    expect(MAX_MUTATIONS_PER_RUN).toBe(96);
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
