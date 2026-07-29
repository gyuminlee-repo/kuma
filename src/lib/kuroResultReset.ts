/**
 * kuroResultReset.ts, KURO 파생 결과물 무효화 패치 (순수 함수)
 *
 * 자동 저장 스냅샷의 `results` 블록(kuroSnapshot.ts buildKuroSnapshot)과 1:1로
 * 맞춘 9개 필드 + `backendDesignStateSynced`를 초기값으로 되돌리는 패치를 만든다.
 * 표(designResults)와 카운터(successCount/totalCount)가 어긋나지 않도록 한 곳에서만
 * 목록을 관리한다.
 *
 * 사용처
 *   - sequenceSlice.loadSequence, 템플릿이 바뀌면 이전 템플릿 기준 결과물 폐기
 *   - sequenceSlice.setSelectedGene, 대상 CDS가 바뀌면 잔기 번호 기준이 바뀌므로 동일
 *   - useAutosaveHydration.discardResultsIfVariantsDiverged, 복원된 결과물 폐기
 *
 * store를 import 하지 않는다(타입만 참조). store-coupled leaf util이 module-eval
 * import cycle을 만든 전례가 있어 순수 모듈로 유지한다.
 *
 * 초기값 출처: designSlice.ts(backendDesignStateSynced/designResults/successCount/
 * totalCount/failedMutations/manuallySwapped/customCandidates/rescuedMutationDetails),
 * exportSlice.ts(plateMappings/dedupInfo).
 */

import type { AppState } from "@/store/types";

/** KURO 파생 결과물 필드를 초기값으로 되돌리는 store 패치를 만든다. */
export function buildKuroResultResetPatch(): Partial<AppState> {
  return {
    designResults: [],
    successCount: 0,
    totalCount: 0,
    failedMutations: [],
    plateMappings: [],
    dedupInfo: {},
    manuallySwapped: {},
    customCandidates: {},
    rescuedMutationDetails: [],
    backendDesignStateSynced: false,
  };
}
