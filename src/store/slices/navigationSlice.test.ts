/**
 * navigationSlice.test.ts — Phase G: 3-major 구조 단위 테스트
 * setMajor / setSubStep prefix 매칭 / markDone
 * [source: spec Phase G — navigationSlice 재구조 (Track A G1)]
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
  it("MAJOR_ORDER contains 3 majors in order (Phase G)", () => {
    expect(MAJOR_ORDER).toEqual(["design", "output", "export"]);
  });

  it("SUBSTEP_ORDER covers 6 sub-steps (4+1+1)", () => {
    const total = Object.values(SUBSTEP_ORDER).reduce(
      (acc, steps) => acc + steps.length,
      0,
    );
    expect(total).toBe(6);
  });

  it("design major has 4 sub-steps (Phase G order)", () => {
    expect(SUBSTEP_ORDER.design).toEqual([
      "design.load",
      "design.mutation",
      "design.params",
      "design.submit",
    ]);
  });

  it("output major has 1 sub-step", () => {
    expect(SUBSTEP_ORDER.output).toEqual(["output.summary"]);
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
    slice.setMajor("output");
    slice.setMajor("design");
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.load");
  });

  it("switching to output major sets output.summary", () => {
    const slice = makeSlice();
    slice.setMajor("output");
    expect(slice.currentMajor).toBe("output");
    expect(slice.currentSubStep).toBe("output.summary");
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

  it("design.submit -> currentMajor becomes design", () => {
    const slice = makeSlice();
    slice.setSubStep("design.submit");
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.submit");
  });

  it("output.summary -> currentMajor becomes output", () => {
    const slice = makeSlice();
    slice.setSubStep("output.summary");
    expect(slice.currentMajor).toBe("output");
    expect(slice.currentSubStep).toBe("output.summary");
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
    expect(slice.stepStatus["design.mutation"].done).toBe(false);
    expect(slice.stepStatus["output.summary"].done).toBe(false);
  });

  it("reachable remains true after markDone", () => {
    const slice = makeSlice();
    slice.markDone("design.submit");
    expect(slice.stepStatus["design.submit"].reachable).toBe(true);
  });
});

describe("goToNextStep (Phase G)", () => {
  it("design.load → goToNextStep → design.mutation", () => {
    const slice = makeSlice();
    slice.setSubStep("design.load");
    slice.goToNextStep();
    expect(slice.currentSubStep).toBe("design.mutation");
    expect(slice.currentMajor).toBe("design");
  });

  it("design.mutation → design.params", () => {
    const slice = makeSlice();
    slice.setSubStep("design.mutation");
    slice.goToNextStep();
    expect(slice.currentSubStep).toBe("design.params");
  });

  it("design.params → design.submit", () => {
    const slice = makeSlice();
    slice.setSubStep("design.params");
    slice.goToNextStep();
    expect(slice.currentSubStep).toBe("design.submit");
  });

  it("design.submit → goToNextStep → output.summary (next major)", () => {
    const slice = makeSlice();
    slice.setSubStep("design.submit");
    slice.goToNextStep();
    expect(slice.currentMajor).toBe("output");
    expect(slice.currentSubStep).toBe("output.summary");
  });

  it("output.summary → goToNextStep → export.all (next major)", () => {
    const slice = makeSlice();
    slice.setSubStep("output.summary");
    slice.goToNextStep();
    expect(slice.currentMajor).toBe("export");
    expect(slice.currentSubStep).toBe("export.all");
  });

  it("export.all → goToNextStep → noop (last step)", () => {
    const slice = makeSlice();
    slice.setSubStep("export.all");
    slice.goToNextStep();
    expect(slice.currentMajor).toBe("export");
    expect(slice.currentSubStep).toBe("export.all");
  });
});

describe("goToPrevStep (Phase G)", () => {
  it("design.load → goToPrevStep → noop (first step)", () => {
    const slice = makeSlice();
    slice.setSubStep("design.load");
    slice.goToPrevStep();
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.load");
  });

  it("design.mutation → goToPrevStep → design.load", () => {
    const slice = makeSlice();
    slice.setSubStep("design.mutation");
    slice.goToPrevStep();
    expect(slice.currentSubStep).toBe("design.load");
  });

  it("output.summary → goToPrevStep → design.submit (prev major last step)", () => {
    const slice = makeSlice();
    slice.setSubStep("output.summary");
    slice.goToPrevStep();
    expect(slice.currentMajor).toBe("design");
    expect(slice.currentSubStep).toBe("design.submit");
  });

  it("export.all → goToPrevStep → output.summary (prev major last step)", () => {
    const slice = makeSlice();
    slice.setSubStep("export.all");
    slice.goToPrevStep();
    expect(slice.currentMajor).toBe("output");
    expect(slice.currentSubStep).toBe("output.summary");
  });
});

describe("canGoNext / canGoPrev (Phase G)", () => {
  it("canGoNext is true at design.load", () => {
    const slice = makeSlice();
    slice.setSubStep("design.load");
    expect(slice.canGoNext()).toBe(true);
  });

  it("canGoNext is false at export.all (last step)", () => {
    const slice = makeSlice();
    slice.setSubStep("export.all");
    expect(slice.canGoNext()).toBe(false);
  });

  it("canGoPrev is false at design.load (first step)", () => {
    const slice = makeSlice();
    slice.setSubStep("design.load");
    expect(slice.canGoPrev()).toBe(false);
  });

  it("canGoPrev is true at design.mutation", () => {
    const slice = makeSlice();
    slice.setSubStep("design.mutation");
    expect(slice.canGoPrev()).toBe(true);
  });

  it("canGoPrev is true at output.summary", () => {
    const slice = makeSlice();
    slice.setSubStep("output.summary");
    expect(slice.canGoPrev()).toBe(true);
  });
});
