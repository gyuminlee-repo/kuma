/**
 * navigationSlice.test.ts — D1.1: 3-major 구조 단위 테스트
 * setMajor / setSubStep prefix 매칭 / markDone
 */

import { describe, it, expect, vi } from "vitest";

// appStore 전체 mock (ipc-kuro dependency 차단)
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import {
  createNavigationSlice,
  MAJOR_ORDER,
  SUBSTEP_ORDER,
} from "./navigationSlice";
import type { NavigationSlice, StepStatus } from "./navigationSlice";

// ---------------------------------------------------------------------------
// Minimal state factory — NavigationSlice만 격리 테스트
// ---------------------------------------------------------------------------

type NavState = NavigationSlice;

function makeSlice(): NavState {
  let state: NavState = {} as NavState;

  const set = (updater: Partial<NavState> | ((s: NavState) => Partial<NavState>)) => {
    const patch =
      typeof updater === "function" ? updater(state) : updater;
    Object.assign(state, patch);
  };

  const get = () => state;

  const creator = createNavigationSlice(
    set as Parameters<typeof createNavigationSlice>[0],
    get as Parameters<typeof createNavigationSlice>[1],
    {} as Parameters<typeof createNavigationSlice>[2],
  );

  Object.assign(state, creator);
  return state;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MAJOR_ORDER / SUBSTEP_ORDER constants", () => {
  it("MAJOR_ORDER contains all 3 majors in order", () => {
    expect(MAJOR_ORDER).toEqual(["design", "plate", "export"]);
  });

  it("SUBSTEP_ORDER covers 6 total sub-steps (4+1+1)", () => {
    const total = Object.values(SUBSTEP_ORDER).reduce(
      (acc, steps) => acc + steps.length,
      0,
    );
    expect(total).toBe(6);
  });

  it("design major has 4 sub-steps", () => {
    expect(SUBSTEP_ORDER.design).toEqual([
      "design.load",
      "design.variant",
      "design.mutation",
      "design.params",
    ]);
  });

  it("plate major has 1 sub-step", () => {
    expect(SUBSTEP_ORDER.plate).toEqual(["plate.layout"]);
  });

  it("export major has 1 sub-step", () => {
    expect(SUBSTEP_ORDER.export).toEqual(["export.all"]);
  });
});

describe("initial state", () => {
  it("starts at design.load", () => {
    const slice = makeSlice();
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.load");
  });

  it("all sub-steps have done=false, reachable=true", () => {
    const slice = makeSlice();
    const allSteps = Object.values(SUBSTEP_ORDER).flat();
    for (const id of allSteps) {
      const s: StepStatus = slice.stepStatus[id];
      expect(s.done, `${id}.done`).toBe(false);
      expect(s.reachable, `${id}.reachable`).toBe(true);
    }
  });
});

describe("setMajor", () => {
  it("MajorStepId 3개 union — design으로 전환", () => {
    const slice = makeSlice();
    slice.setMajor("design");
    expect(slice.currentMajor).toBe("design");
  });

  it("setMajor('design') -> currentSubStep becomes design.load", () => {
    const slice = makeSlice();
    slice.setMajor("plate");
    slice.setMajor("design");
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.load");
  });

  it("switching to plate major sets plate.layout", () => {
    const slice = makeSlice();
    slice.setMajor("plate");
    expect(slice.currentMajor).toBe("plate");
    expect(slice.currentSubStep).toBe("plate.layout");
  });

  it("switching to export major sets export.all", () => {
    const slice = makeSlice();
    slice.setMajor("export");
    expect(slice.currentMajor).toBe("export");
    expect(slice.currentSubStep).toBe("export.all");
  });
});

describe("setSubStep -- prefix 매칭으로 major 자동 추론", () => {
  it("design.mutation -> currentMajor becomes design", () => {
    const slice = makeSlice();
    slice.setSubStep("design.mutation");
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.mutation");
  });

  it("plate.layout -> currentMajor becomes plate", () => {
    const slice = makeSlice();
    slice.setSubStep("plate.layout");
    expect(slice.currentMajor).toBe("plate");
    expect(slice.currentSubStep).toBe("plate.layout");
  });

  it("export.all -> currentMajor becomes export", () => {
    const slice = makeSlice();
    slice.setSubStep("export.all");
    expect(slice.currentMajor).toBe("export");
    expect(slice.currentSubStep).toBe("export.all");
  });

  it("unknown sub-step ID is ignored -- state unchanged", () => {
    const slice = makeSlice();
    const before = { major: slice.currentMajor, sub: slice.currentSubStep };
    // Cast to bypass TypeScript type check in test
    (slice.setSubStep as (id: string) => void)("unknown.step");
    expect(slice.currentMajor).toBe(before.major);
    expect(slice.currentSubStep).toBe(before.sub);
  });
});

describe("markDone", () => {
  it("marks the given sub-step done", () => {
    const slice = makeSlice();
    slice.markDone("design.load");
    expect(slice.stepStatus["design.load"].done).toBe(true);
  });

  it("does not affect other sub-steps", () => {
    const slice = makeSlice();
    slice.markDone("design.load");
    expect(slice.stepStatus["design.variant"].done).toBe(false);
    expect(slice.stepStatus["plate.layout"].done).toBe(false);
  });

  it("reachable remains true after markDone", () => {
    const slice = makeSlice();
    slice.markDone("design.params");
    expect(slice.stepStatus["design.params"].reachable).toBe(true);
  });
});
