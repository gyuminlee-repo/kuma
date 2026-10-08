import { describe, expect, it } from "vitest";
import { resizeEvolveproSelection } from "./evolveproSelection";

// A CSV loaded at the default count seeds 95 selected and the sidecar sends
// those plus a buffer of at most 50 more (EVOLVEPRO_RANKED_BUFFER).
const ranked = Array.from({ length: 145 }, (_, i) => ({ variant: `V${i + 1}` }));
const seeded = ranked.slice(0, 95).map((c) => c.variant);

describe("resizeEvolveproSelection", () => {
  it("shrinks to the first variants in rank order", () => {
    expect(resizeEvolveproSelection(seeded, ranked, 50)).toEqual(seeded.slice(0, 50));
  });

  it("grows past one plate from the loaded buffer", () => {
    const out = resizeEvolveproSelection(seeded, ranked, 120);
    expect(out).toHaveLength(120);
    expect(out).toEqual(ranked.slice(0, 120).map((c) => c.variant));
  });

  it("stops at the buffer when asked for more than was loaded", () => {
    expect(resizeEvolveproSelection(seeded, ranked, 192)).toHaveLength(145);
  });

  it("keeps an unchanged count unchanged", () => {
    expect(resizeEvolveproSelection(seeded, ranked, 95)).toEqual(seeded);
  });

  it("orders by rank and puts unranked entries last", () => {
    const out = resizeEvolveproSelection(["V3", "X9", "V1"], ranked, 4);
    expect(out).toEqual(["V1", "V3", "X9", "V2"]);
  });
});
