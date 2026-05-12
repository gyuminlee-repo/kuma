/**
 * navigationSlice.test.ts — Phase C Stage 1 단위 테스트
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

  // set must update the shared `state` variable AND the slice's own methods
  // so subsequent calls to methods see the updated state.
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

  // Initialize state with the creator's initial values
  Object.assign(state, creator);
  return state;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("MAJOR_ORDER / SUBSTEP_ORDER constants", () => {
  it("MAJOR_ORDER contains all 4 majors in order", () => {
    expect(MAJOR_ORDER).toEqual(["variant", "sdm", "plate", "export"]);
  });

  it("SUBSTEP_ORDER covers 16 total sub-steps (5+5+3+3)", () => {
    const total = Object.values(SUBSTEP_ORDER).reduce(
      (acc, steps) => acc + steps.length,
      0,
    );
    expect(total).toBe(16);
  });
});

describe("initial state", () => {
  it("starts at variant.load", () => {
    const slice = makeSlice();
    expect(slice.currentMajor).toBe("variant");
    expect(slice.currentSubStep).toBe("variant.load");
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
  it("switches to first sub-step of the given major", () => {
    const slice = makeSlice();

    slice.setMajor("sdm");
    expect(slice.currentMajor).toBe("sdm");
    expect(slice.currentSubStep).toBe("sdm.mutations");
  });

  it("switching to plate major sets plate.size", () => {
    const slice = makeSlice();
    slice.setMajor("plate");
    expect(slice.currentMajor).toBe("plate");
    expect(slice.currentSubStep).toBe("plate.size");
  });

  it("switching to export major sets export.format", () => {
    const slice = makeSlice();
    slice.setMajor("export");
    expect(slice.currentSubStep).toBe("export.format");
  });
});

describe("setSubStep — prefix 매칭으로 major 자동 추론", () => {
  it("sdm.run → currentMajor becomes sdm", () => {
    const slice = makeSlice();
    slice.setSubStep("sdm.run");
    expect(slice.currentMajor).toBe("sdm");
    expect(slice.currentSubStep).toBe("sdm.run");
  });

  it("plate.layout → currentMajor becomes plate", () => {
    const slice = makeSlice();
    slice.setSubStep("plate.layout");
    expect(slice.currentMajor).toBe("plate");
    expect(slice.currentSubStep).toBe("plate.layout");
  });

  it("export.workspace → currentMajor becomes export", () => {
    const slice = makeSlice();
    slice.setSubStep("export.workspace");
    expect(slice.currentMajor).toBe("export");
    expect(slice.currentSubStep).toBe("export.workspace");
  });

  it("unknown sub-step ID is ignored — state unchanged", () => {
    const slice = makeSlice();
    const before = { major: slice.currentMajor, sub: slice.currentSubStep };
    slice.setSubStep("unknown.step");
    expect(slice.currentMajor).toBe(before.major);
    expect(slice.currentSubStep).toBe(before.sub);
  });
});

describe("markDone", () => {
  it("marks the given sub-step done", () => {
    const slice = makeSlice();
    slice.markDone("variant.load");
    expect(slice.stepStatus["variant.load"].done).toBe(true);
  });

  it("does not affect other sub-steps", () => {
    const slice = makeSlice();
    slice.markDone("variant.load");
    expect(slice.stepStatus["variant.select"].done).toBe(false);
    expect(slice.stepStatus["sdm.mutations"].done).toBe(false);
  });

  it("reachable remains true after markDone", () => {
    const slice = makeSlice();
    slice.markDone("sdm.run");
    expect(slice.stepStatus["sdm.run"].reachable).toBe(true);
  });
});
