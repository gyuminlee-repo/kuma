import { describe, it, expect } from "vitest";
import {
  STAGE_RELAXATION_TABLE,
  getStageRelaxation,
  getStageParams,
} from "../primerSuggestion";

describe("STAGE_RELAXATION_TABLE", () => {
  it("defines all 4 stages with required keys", () => {
    for (const stage of [1, 2, 3, 4] as const) {
      const r = STAGE_RELAXATION_TABLE[stage];
      expect(r).toHaveProperty("lengthDelta");
      expect(r).toHaveProperty("gcDelta");
      expect(r).toHaveProperty("tmTolDelta");
    }
  });
  it("monotonically widens stage 1 to 4", () => {
    expect(STAGE_RELAXATION_TABLE[1].lengthDelta).toBeLessThanOrEqual(
      STAGE_RELAXATION_TABLE[4].lengthDelta,
    );
    expect(STAGE_RELAXATION_TABLE[1].tmTolDelta).toBeLessThanOrEqual(
      STAGE_RELAXATION_TABLE[4].tmTolDelta,
    );
  });
});

describe("getStageRelaxation", () => {
  it("returns table entry for valid stage", () => {
    expect(getStageRelaxation(3)).toEqual(STAGE_RELAXATION_TABLE[3]);
  });
});

describe("getStageParams", () => {
  const base = {
    tmFwd: 62, tmRev: 58, tmOverlap: 42,
    gcMin: 40, gcMax: 60,
    fwdLenMin: 22, fwdLenMax: 30,
    revLenMin: 22, revLenMax: 28,
    baseTol: 3.0,
  };
  it("stage 1 widens length only", () => {
    const p = getStageParams(base, 1);
    expect(p.fwdLenMin).toBe(20);
    expect(p.fwdLenMax).toBe(32);
    expect(p.gcMin).toBe(40);
    expect(p.tolMax).toBe(3.0);
  });
  it("stage 4 caps tol at 10.0", () => {
    const p = getStageParams({ ...base, baseTol: 6.0 }, 4);
    expect(p.tolMax).toBe(10.0);
  });
  it("stage 3 with base 3.0 yields tol 5.0", () => {
    const p = getStageParams(base, 3);
    expect(p.tolMax).toBe(5.0);
  });
});
