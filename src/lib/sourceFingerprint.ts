/**
 * sourceFingerprint.ts, 자동 저장 재도출 건너뛰기용 파일 지문 (순수 유틸)
 *
 * 서열 파일과 EVOLVEpro CSV가 자동 저장 시점 이후 바뀌지 않았으면, 복원 시
 * loadSequence/loadEvolveproCsv를 다시 돌릴 이유가 없다(그 재실행이 사이드효과로
 * seqInfo/mutationText 등을 초기화하고 늦게 착지해 복원된 값을 덮어쓴다).
 * "바뀌지 않았다"를 판정하는 근거로 파일 내용 해시 대신 `{ size, mtimeMs }`를
 * 쓴다. 대용량 FASTA/CSV에서 해시 비용이 더 크고, 그 정도 정밀도가 이 용도에는
 * 충분하다(오탐 시 안전한 쪽, 재도출 폴백, 으로 떨어진다).
 *
 * `stat`은 `src-tauri/capabilities/default.json`의 `fs:allow-stat`으로 이미
 * 허용돼 있어 권한 변경 없이 쓸 수 있다.
 *
 * 공유 드라이브(WSL2의 drvfs로 마운트된 `/mnt/d` 등, 네트워크 드라이브도
 * 마찬가지) 위 파일은 mtime 정밀도가 로컬 파일시스템(ext4 등)과 다를 수
 * 있다(초 단위로 잘리는 등). 저장 시점과 복원 시점의 stat이 같은 파일
 * 시스템 위에서 이뤄지는 정상 사용에서는 문제가 되지 않지만, 정밀도가
 * 달라 저장했던 지문과 다시 읽은 지문이 어긋나더라도 `fingerprintsEqual`이
 * false를 돌려줄 뿐이다. 그 결과는 재도출 폴백이며 안전하다(파일이 실제로는
 * 그대로인데 재도출을 한 번 더 하는 손해만 있고, 데이터 손실은 없다).
 */

import { stat } from "@tauri-apps/plugin-fs";

export interface SourceFingerprint {
  size: number;
  mtimeMs: number;
}

/**
 * 파일 지문을 읽는다. 경로가 비어 있거나 stat이 실패하면(파일 없음, 권한 등)
 * null을 돌려준다. null은 "지문 없음"이며 호출부는 이를 항상 불일치로 취급해
 * 재도출 폴백 경로를 태워야 한다(파일 없음을 조용히 "일치"로 오판하지 않는다).
 */
export async function fingerprintSource(filepath: string): Promise<SourceFingerprint | null> {
  if (!filepath) return null;
  try {
    const info = await stat(filepath);
    const mtimeMs = info.mtime ? info.mtime.getTime() : 0;
    return { size: info.size, mtimeMs };
  } catch {
    return null;
  }
}

/**
 * 두 지문이 같은 파일 상태를 가리키는지. 어느 한쪽이라도 null이면 false다
 * (지문 없음은 "모른다"이며 "같다"가 아니다).
 */
export function fingerprintsEqual(
  a: SourceFingerprint | null | undefined,
  b: SourceFingerprint | null | undefined,
): boolean {
  if (!a || !b) return false;
  return a.size === b.size && a.mtimeMs === b.mtimeMs;
}
