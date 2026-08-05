/**
 * navigationSlice.test.ts — Task D1.2 단위 테스트
 *
 * NavigationSlice와 PhaseSlice의 sub-step 자동 리셋 동작을 검증한다.
 */

import { beforeEach, describe, expect, it } from "vitest";
import type { AppState } from "../types";
import { createNavigationSlice, MAME_SUBSTEP_ORDER } from "./navigationSlice";
import { createPhaseSlice } from "./phaseSlice";

// localStorage mock
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();
Object.defineProperty(globalThis, "localStorage", { value: localStorageMock });

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = { ...initial };

  const set = (
    updater: Partial<AppState> | ((current: AppState) => Partial<AppState>),
  ) => {
    const updates =
      typeof updater === "function"
        ? updater(state as AppState)
        : updater;
    Object.assign(state, updates);
  };
  const get = () => state as AppState;
  const stub = {} as Parameters<typeof createNavigationSlice>[2];

  const navSlice = createNavigationSlice(
    set as Parameters<typeof createNavigationSlice>[0],
    get as Parameters<typeof createNavigationSlice>[1],
    stub,
  );
  const phaseSlice = createPhaseSlice(
    set as Parameters<typeof createPhaseSlice>[0],
    get as Parameters<typeof createPhaseSlice>[1],
    stub,
  );

  Object.assign(state, navSlice, phaseSlice, initial);
  return state as AppState;
}

describe("MAME_SUBSTEP_ORDER", () => {
  it("각 phase에 정확한 sub-step 배열을 가진다", () => {
    expect(MAME_SUBSTEP_ORDER.setup).toEqual(["setup.files"]);
    expect(MAME_SUBSTEP_ORDER.analyze).toEqual([
      "analyze.inputs",
      "analyze.review",
    ]);
    expect(MAME_SUBSTEP_ORDER.janus).toEqual(["janus.settings"]);
    expect(MAME_SUBSTEP_ORDER.activity).toEqual([
      "activity.ingest",
      "activity.signals",
    ]);
  });
});

describe("NavigationSlice — setMameSubStep", () => {
  let store: AppState;

  beforeEach(() => {
    localStorageMock.clear();
    store = makeStore();
  });

  it("초기값은 setup.files이다", () => {
    expect(store.currentMameSubStep).toBe("setup.files");
  });

  it("setMameSubStep으로 임의 sub-step을 설정할 수 있다", () => {
    store.setMameSubStep("analyze.plate");
    expect(store.currentMameSubStep).toBe("analyze.plate");
  });

  it("setMameSubStep으로 activity sub-step을 설정할 수 있다", () => {
    store.setMameSubStep("activity.mergeExport");
    expect(store.currentMameSubStep).toBe("activity.mergeExport");
  });
});

describe("PhaseSlice — setMamePhase sub-step 자동 리셋", () => {
  let store: AppState;

  beforeEach(() => {
    localStorageMock.clear();
    store = makeStore();
  });

  it("setMamePhase('analyze') → currentMameSubStep이 analyze.inputs로 리셋된다", () => {
    store.setMameSubStep("setup.design");
    store.setMamePhase("analyze");
    expect(store.mamePhase).toBe("analyze");
    expect(store.currentMameSubStep).toBe("analyze.inputs");
  });

  it("setMamePhase('activity') → currentMameSubStep이 activity.ingest로 리셋된다", () => {
    store.setMamePhase("activity");
    expect(store.mamePhase).toBe("activity");
    expect(store.currentMameSubStep).toBe("activity.ingest");
  });

  it("setMamePhase('setup') → currentMameSubStep이 setup.files로 리셋된다", () => {
    store.setMameSubStep("analyze.plate");
    store.setMamePhase("setup");
    expect(store.mamePhase).toBe("setup");
    expect(store.currentMameSubStep).toBe("setup.files");
  });

  it("phase 전환 chain: setup → analyze → janus → activity 순서로 sub-step 리셋", () => {
    store.setMamePhase("setup");
    expect(store.currentMameSubStep).toBe("setup.files");

    store.setMamePhase("analyze");
    expect(store.currentMameSubStep).toBe("analyze.inputs");

    store.setMamePhase("janus");
    expect(store.currentMameSubStep).toBe("janus.settings");

    store.setMamePhase("activity");
    expect(store.currentMameSubStep).toBe("activity.ingest");
  });
});

/**
 * Janus 장비 설정이 step 3 으로 분리되면서 analyze 와 activity 사이에 phase 가 하나
 * 늘었다. 시퀀싱만 필요한 운용자는 step 2 에서 멈추지만, 순차 이동은 새 단계를
 * 건너뛰지 않고 지나가야 한다.
 */
describe("NavigationSlice — janus phase 경계", () => {
  let store: AppState;

  beforeEach(() => {
    localStorageMock.clear();
    store = makeStore();
  });

  it("analyze.review 다음은 janus.settings 이다", () => {
    store.setMamePhase("analyze");
    store.setMameSubStep("analyze.review");

    store.goToNextStep();

    expect(store.mamePhase).toBe("janus");
    expect(store.currentMameSubStep).toBe("janus.settings");
  });

  it("janus.settings 다음은 activity.ingest 이다", () => {
    store.setMamePhase("janus");

    store.goToNextStep();

    expect(store.mamePhase).toBe("activity");
    expect(store.currentMameSubStep).toBe("activity.ingest");
  });

  it("activity.ingest 이전은 janus.settings 이다", () => {
    store.setMamePhase("activity");

    store.goToPrevStep();

    expect(store.mamePhase).toBe("janus");
    expect(store.currentMameSubStep).toBe("janus.settings");
  });

  it("janus.settings 이전은 analyze.review 이다", () => {
    store.setMamePhase("janus");

    store.goToPrevStep();

    expect(store.mamePhase).toBe("analyze");
    expect(store.currentMameSubStep).toBe("analyze.review");
  });

  it("저장된 janus phase 를 그대로 복원한다", () => {
    localStorageMock.setItem("kuma:mame:phase", "janus");
    const restored = makeStore();
    expect(restored.mamePhase).toBe("janus");
  });

  it("알 수 없는 저장값은 기존과 동일하게 analyze 로 되돌린다", () => {
    localStorageMock.setItem("kuma:mame:phase", "janus-typo");
    const restored = makeStore();
    expect(restored.mamePhase).toBe("analyze");
  });
});
