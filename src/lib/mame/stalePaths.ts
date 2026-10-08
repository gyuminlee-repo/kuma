/**
 * stalePaths.ts, 자동 저장에서 복원한 MAME 입력 경로 중 사라진 것 걸러내기
 *
 * 자동 저장 스냅샷은 사용자가 파일 다이얼로그로 고른 절대 경로를 그대로 담는다
 * (`lib/mame/autosaveSnapshot.ts`). 프로젝트 폴더를 옮기거나 다른 PC에서 열면
 * 그 경로는 더 이상 존재하지 않는다.
 *
 * 문제는 복원이 그 죽은 경로를 store 에 그대로 세팅한다는 점이다
 * (`hooks/useAutosaveHydration.ts` applyMameSnapshot). 뒤이어 도는 자동 감지는
 * **빈 필드만** 채우므로, 값이 들어차 있는 죽은 경로는 "이미 채워짐"으로 판정돼
 * 감지가 통째로 건너뛰어진다. 파일이 프로젝트 폴더 안에 멀쩡히 있어도 못 찾는다.
 *
 * 그래서 복원 직후 존재 검사를 한 번 돌려 사라진 필드를 비운다. 비우면 기존 자동
 * 감지가 같은 파일을 다시 찾아 채운다. raw MinKNOW run 폴더처럼 프로젝트 밖에
 * 있어 다시 찾지 못하는 항목은 이름을 그대로 돌려주어, 호출부가 무엇을 다시
 * 지정해야 하는지 사용자에게 알릴 수 있게 한다.
 *
 * fs 접근은 주입받는다. store 를 import 하지 않는 순수 모듈로 유지해 테스트에서
 * Tauri 없이 돌린다 (store-coupled leaf util 이 module-eval import cycle 을 만든
 * 전례가 있다).
 */

/** 복원된 MAME 입력 경로 필드. 값이 빈 문자열이면 애초에 검사 대상이 아니다. */
export interface RestoredMamePaths {
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  customBarcodesPath: string;
  sequencingSummaryPath: string;
}

export type MamePathField = keyof RestoredMamePaths;

/** 필드별 사용자 표기용 i18n 키. 자동 감지 메시지가 쓰는 키와 같은 것을 재사용한다. */
export const MAME_PATH_LABEL_KEYS: Record<MamePathField, string> = {
  inputDir: "autosaveHydration.fieldRunFolder",
  expectedPath: "autosaveHydration.fieldExpected",
  referencePath: "autosaveHydration.fieldReference",
  customBarcodesPath: "autosaveHydration.fieldCustomBarcodes",
  sequencingSummaryPath: "autosaveHydration.fieldSequencingSummary",
};

const ALL_FIELDS: MamePathField[] = [
  "inputDir",
  "expectedPath",
  "referencePath",
  "customBarcodesPath",
  "sequencingSummaryPath",
];

/**
 * 존재하지 않는 경로를 가진 필드 목록을 돌려준다.
 *
 * 빈 값은 건너뛴다(비어 있으면 이미 자동 감지 대상이다). 존재 검사 자체가 실패한
 * 경로는 **사라진 것으로 취급하지 않는다**. 권한 오류나 네트워크 드라이브 지연으로
 * 멀쩡한 경로를 지워 버리면 복원이 오히려 나빠지기 때문이다. 판단이 서지 않을 때는
 * 사용자가 고른 값을 남기는 쪽을 택한다.
 *
 * @param paths   복원 직후의 경로 필드 모음.
 * @param exists  경로 존재 여부. Tauri `plugin-fs` 의 `exists` 를 주입한다.
 */
export async function findStaleMamePaths(
  paths: Partial<RestoredMamePaths>,
  exists: (path: string) => Promise<boolean>,
): Promise<MamePathField[]> {
  const stale: MamePathField[] = [];
  for (const field of ALL_FIELDS) {
    const value = paths[field];
    if (!value) continue;
    let present: boolean;
    try {
      present = await exists(value);
    } catch {
      // 검사 실패는 부재의 증거가 아니다. 값을 남긴다.
      continue;
    }
    if (!present) stale.push(field);
  }
  return stale;
}
