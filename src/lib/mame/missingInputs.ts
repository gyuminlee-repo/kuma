/**
 * missingInputs.ts, 복원 후 되찾지 못한 MAME 입력 목록
 *
 * 프로젝트 폴더 안의 입력은 자동 감지가 다시 찾는다(`useAutosaveHydration`).
 * 되찾을 수 없는 것은 폴더 밖에 있던 원천 입력, 실질적으로 raw MinKNOW run
 * 폴더다. 수 GB라 프로젝트에 담을 수 없으므로 스냅샷에는 참조만 적히고
 * (`lib/pathRef.ts` external), 옮긴 환경에서는 사용자가 다시 지정해야 한다.
 *
 * 지금까지는 이것이 4초짜리 상태 메시지로만 지나갔다. 사라진 줄 모른 채 분석을
 * 돌리면 그때서야 실패한다. 그래서 목록을 남겨 두고 배너가 해소될 때까지
 * 붙잡아 둔다.
 *
 * 저장했던 크기·수정시각을 함께 들고 있다가 다시 고른 파일과 대조한다. 같은
 * 이름의 다른 run 을 붙이는 사고가 실제 위험이라, 다르면 경고를 띄운다.
 */

import { create } from "zustand";
import type { MamePathField } from "./stalePaths";

export interface MissingInput {
  field: MamePathField;
  /** 원래 파일·폴더 이름. 사용자가 무엇을 찾아야 하는지 알려 준다. */
  name: string;
  /** 스냅샷에 적혀 있던 크기(바이트). 재지정 대조용. */
  size?: number;
  /** 스냅샷에 적혀 있던 수정 시각(ISO). 재지정 대조용. */
  mtime?: string;
}

interface MissingInputsState {
  items: MissingInput[];
  /** 복원 직후 한 번 채운다. 이전 프로젝트의 잔여 항목을 남기지 않는다. */
  setMissing: (items: MissingInput[]) => void;
  /** 사용자가 다시 지정한 항목을 목록에서 뺀다. */
  resolve: (field: MamePathField) => void;
  clear: () => void;
}

export const useMissingInputs = create<MissingInputsState>((set) => ({
  items: [],
  setMissing: (items) => set({ items }),
  resolve: (field) =>
    set((s) => ({ items: s.items.filter((i) => i.field !== field) })),
  clear: () => set({ items: [] }),
}));

/** 사람이 읽는 크기. 정확한 바이트가 아니라 "같은 파일인가" 판단용이다. */
export function formatSize(bytes: number | undefined): string | null {
  if (bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return null;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

/**
 * 다시 지정한 대상이 원래 것과 같아 보이는지 판단한다.
 *
 * 크기를 기록해 두지 않았으면 (`expected.size === undefined`) 대조할 근거가
 * 없으므로 통과시킨다. 없는 근거로 사용자를 막지 않는다.
 *
 * 폴더는 크기를 재지 않으므로 이름만 본다. run 폴더 재지정이 이 경우다.
 */
export function looksLikeSameTarget(
  expected: MissingInput,
  actual: { name: string; size?: number },
): boolean {
  if (expected.size !== undefined && actual.size !== undefined) {
    return expected.size === actual.size;
  }
  return expected.name === actual.name;
}
