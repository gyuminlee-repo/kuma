import { describe, expect, it } from "vitest";
import type { PlateMapping } from "@/types/models";
import {
  fitRoundPicks,
  normalizeRoundPicks,
  persistRoundPicks,
  plateOptionCount,
  roundPickIssue,
  splitIntoRounds,
  usedBeforeRound,
  type RoundPick,
} from "./plateRounds";

// Boundary counts from `.cross-layer-sync.json` (plate-well-capacity): 95, 96
// and 97 straddle the split into rounds, 191, 192 and 193 the second, 288 and
// 289 the third. There is no design bound: each round names its own Echo
// source plate. A fixture below 96 gives the same answer with or without a
// split.

function design(n: number, sharedRev = false) {
  const mappings: PlateMapping[] = [];
  const dedupInfo: Record<string, string[]> = {};
  for (let i = 0; i < n; i++) {
    const mut = `M${i + 1}A`;
    mappings.push({ well: "", primer_name: `${mut}_F`, sequence: `F${i}`, primer_type: "forward", mutation: mut });
    // With sharedRev, mutations 96 and 97 (indices 95, 96) share one reverse
    // primer, so it straddles the round boundary.
    const revSeq = sharedRev && (i === 95 || i === 96) ? "R_shared" : `R${i}`;
    if (!dedupInfo[revSeq]) {
      dedupInfo[revSeq] = [];
      mappings.push({ well: "", primer_name: `${mut}_R`, sequence: revSeq, primer_type: "reverse", mutation: mut });
    }
    dedupInfo[revSeq]!.push(mut);
  }
  return { mappings, dedupInfo };
}

const PLATE = /^[A-H](?:[1-9]|1[0-2])$/;

describe("splitIntoRounds", () => {
  it.each([
    [95, [95]],
    [96, [96]],
    [97, [96, 1]],
    [191, [96, 95]],
    [192, [96, 96]],
    [193, [96, 96, 1]],
    [288, [96, 96, 96]],
    [289, [96, 96, 96, 1]],
  ])("%i forward primers split into rounds of %j", (n, sizes) => {
    const { mappings, dedupInfo } = design(n);
    const rounds = splitIntoRounds(mappings, dedupInfo, null);
    expect(rounds.map((r) => r.mappings.filter((m) => m.primer_type === "forward").length)).toEqual(sizes);
    expect(rounds.map((r) => r.label)).toEqual(sizes.map((_, k) => `R${k + 1}`));
    for (const round of rounds) {
      for (const dir of ["forward", "reverse"]) {
        const wells = round.mappings.filter((m) => m.primer_type === dir).map((m) => m.well);
        expect(wells.every((w) => PLATE.test(w))).toBe(true);
        expect(new Set(wells).size).toBe(wells.length);
      }
      expect(round.mappings.some((m) => m.well.startsWith("P2-"))).toBe(false);
    }
  });

  it("numbers a third round and restarts its wells at A1", () => {
    const { mappings, dedupInfo } = design(193);
    const rounds = splitIntoRounds(mappings, dedupInfo, null);
    expect(rounds).toHaveLength(3);
    expect(rounds[2]).toMatchObject({ label: "R3", from: 193, to: 193 });
    expect(rounds[2]!.mappings.filter((m) => m.primer_type === "forward")).toEqual([
      expect.objectContaining({ mutation: "M193A", well: "A1" }),
    ]);
  });

  it("follows the table sort and restarts wells at A1 in round 2", () => {
    const { mappings, dedupInfo } = design(97);
    const sorted = mappings.filter((m) => m.primer_type === "forward").map((m) => m.mutation).reverse();
    const [r1, r2] = splitIntoRounds(mappings, dedupInfo, sorted);
    expect(r1!.mappings[0]).toMatchObject({ mutation: "M97A", well: "A1" });
    expect(r2!.mappings.filter((m) => m.primer_type === "forward")).toEqual([
      expect.objectContaining({ mutation: "M1A", well: "A1" }),
    ]);
    expect(r2!.from).toBe(97);
    expect(r2!.to).toBe(97);
  });

  it("writes a reverse primer shared across the boundary in both rounds", () => {
    const { mappings, dedupInfo } = design(97, true);
    const [r1, r2] = splitIntoRounds(mappings, dedupInfo, null);
    const revSeqs = (r: typeof r1) => r!.mappings.filter((m) => m.primer_type === "reverse").map((m) => m.sequence);
    expect(revSeqs(r1)).toContain("R_shared");
    expect(revSeqs(r2)).toEqual(["R_shared"]);
    expect(r1!.dedupInfo["R_shared"]).toEqual(["M96A"]);
    expect(r2!.dedupInfo["R_shared"]).toEqual(["M97A"]);
  });
});

const pick = (plate: number | null, quadrant: "A1" | "A2" | null): RoundPick => ({ plate, quadrant });

describe("usedBeforeRound", () => {
  it("counts only earlier rounds on the same plate", () => {
    const picks = [pick(1, "A2"), pick(1, null), pick(2, "A1"), pick(2, null)];
    expect(usedBeforeRound(picks, 0, [])).toEqual([]);
    expect(usedBeforeRound(picks, 1, [])).toEqual(["A2"]);
    // Round 3 is on plate 2, a new plate: plate 1's A2 is not spent there.
    expect(usedBeforeRound(picks, 2, [])).toEqual([]);
    expect(usedBeforeRound(picks, 3, [])).toEqual(["A1"]);
  });

  it("applies the parities the operator marked as spent to plate 1 only", () => {
    const picks = [pick(1, "A2"), pick(2, "A1")];
    expect(usedBeforeRound(picks, 0, ["A1"])).toEqual(["A1"]);
    expect(usedBeforeRound(picks, 1, ["A1"])).toEqual([]);
  });

  it("has nothing spent for a round with no plate picked", () => {
    expect(usedBeforeRound([pick(null, "A1")], 0, ["A1"])).toEqual([]);
  });
});

describe("roundPickIssue", () => {
  it("asks for the plate and the parity, with no default", () => {
    expect(roundPickIssue([], 0, [])).toBe("plateUnpicked");
    expect(roundPickIssue([pick(null, "A1")], 0, [])).toBe("plateUnpicked");
    expect(roundPickIssue([pick(1, null)], 0, [])).toBe("quadrantUnpicked");
    expect(roundPickIssue([pick(1, "A1")], 0, [])).toBeNull();
  });

  it("refuses the same plate and parity on two rounds, in either order", () => {
    const picks = [pick(2, "A1"), pick(1, "A2"), pick(2, "A1")];
    expect(roundPickIssue(picks, 0, [])).toBe("duplicate");
    expect(roundPickIssue(picks, 2, [])).toBe("duplicate");
    expect(roundPickIssue(picks, 1, [])).toBeNull();
  });

  it("allows A1 on plate 2 whatever plate 1 has spent", () => {
    const picks = [pick(1, "A1"), pick(1, "A2"), pick(2, "A1")];
    expect(roundPickIssue(picks, 2, ["A1", "A2"])).toBeNull();
    expect(roundPickIssue([pick(1, "A1")], 0, ["A1"])).toBe("quadrantAlreadyUsed");
  });
});

describe("plateOptionCount", () => {
  it("offers at least as many plates as rounds", () => {
    expect(plateOptionCount(0)).toBe(1);
    expect(plateOptionCount(2)).toBe(2);
    expect(plateOptionCount(5)).toBe(5);
  });
});

describe("normalizeRoundPicks", () => {
  it.each([
    [undefined, undefined, []],
    [null, undefined, []],
    ["A1", undefined, []],
    // A project saved before several plates holds two parities and no plates:
    // both rounds were on plate 1.
    [[], undefined, [pick(1, null), pick(1, null)]],
    [["A1"], undefined, [pick(1, "A1"), pick(1, null)]],
    [["A2", "A1"], undefined, [pick(1, "A2"), pick(1, "A1")]],
    [["A1", "A1"], undefined, [pick(1, "A1"), pick(1, null)]],
    [["A13", "B1"], undefined, [pick(1, null), pick(1, null)]],
    [[1, "A2"], undefined, [pick(1, null), pick(1, "A2")]],
    // The current format: a plate list beside the parity list.
    [["A1", "A1", "A2"], [1, 2, 2], [pick(1, "A1"), pick(2, "A1"), pick(2, "A2")]],
    [["A1", "A1"], [2, 2], [pick(2, "A1"), pick(2, null)]],
    [["A1", null], [0, 1.5], [pick(null, "A1"), pick(null, null)]],
    [[null, null, null], [null, "2", 3], [pick(null, null), pick(null, null), pick(3, null)]],
  ])("%j with plates %j reads as %j", (quadrants, plates, want) => {
    expect(normalizeRoundPicks(quadrants, plates)).toEqual(want);
  });

  it("round-trips through the persisted pair of lists", () => {
    const picks = [pick(1, "A2"), pick(2, "A1"), pick(null, null)];
    const saved = persistRoundPicks(picks);
    expect(saved).toEqual({ quadrants: ["A2", "A1", null], plates: [1, 2, null] });
    expect(normalizeRoundPicks(saved.quadrants, saved.plates)).toEqual(picks);
  });
});

describe("fitRoundPicks", () => {
  it("unpicks a round whose plate is past the plates offered for this many rounds", () => {
    const picks = [pick(5, "A1"), pick(3, "A2"), pick(1, "A1")];
    expect(fitRoundPicks(picks, 3)).toEqual([pick(null, null), pick(3, "A2"), pick(1, "A1")]);
  });

  it("drops picks for rounds that no longer exist and fills missing ones", () => {
    expect(fitRoundPicks([pick(1, "A1"), pick(2, "A1"), pick(1, "A2")], 2)).toEqual([
      pick(1, "A1"),
      pick(2, "A1"),
    ]);
    expect(fitRoundPicks([pick(1, "A1")], 2)).toEqual([pick(1, "A1"), pick(null, null)]);
  });

  it("returns the same list when nothing changes, so a caller can skip a write", () => {
    const picks = [pick(1, "A1"), pick(2, null)];
    expect(fitRoundPicks(picks, 2)).toBe(picks);
  });
});
