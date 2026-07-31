/**
 * projectPath.ts, 자동 저장 스냅샷용 이식 가능 경로 변환 (순수 함수)
 *
 * 자동 저장 스냅샷은 사용자가 파일 다이얼로그로 고른 경로를 담는다. 그 값을
 * 절대 경로 그대로 저장하면 프로젝트 폴더를 다른 PC로 옮겼을 때 복원이 깨진다.
 * 산출물 매니페스트(`lib/workspace/api.ts`)는 이미 상대 경로로 기록하므로,
 * 스냅샷도 같은 성질을 갖게 하는 것이 이 모듈의 목적이다.
 *
 * 규칙:
 * - 프로젝트 폴더 **안**을 가리키면 `project://` 접두사 + 상대 경로로 저장한다.
 * - 프로젝트 폴더 **밖**을 가리키면 절대 경로 그대로 둔다. 옮긴 뒤 되살릴 수
 *   없는 값이라는 사실을 숨기지 않기 위해서다. 복원 측이 존재를 확인해 사용자에게
 *   알린다.
 * - 접두사가 없는 저장값은 구 스냅샷(전부 절대 경로)이므로 그대로 돌려준다.
 *
 * 구분자는 `/`로 통일한다. Tauri IPC가 절대 경로를 그대로 받으며, Windows도
 * 정방향 슬래시를 수용한다. `lib/workspace/api.ts` 의 상대 경로 계산과 같은 규약이다.
 */

/** 프로젝트 폴더 기준 상대 경로임을 나타내는 접두사. */
export const PROJECT_PATH_PREFIX = "project://";

/** 역슬래시를 정방향으로 바꾸고 끝의 구분자를 제거한다. */
function normalizeBase(value: string): string {
  return value.replace(/\\/g, "/").replace(/\/+$/, "");
}

/** 저장값이 프로젝트 상대 경로 형식인지. */
export function isPortablePath(value: string): boolean {
  return value.startsWith(PROJECT_PATH_PREFIX);
}

/**
 * 절대 경로를 스냅샷에 담을 형태로 바꾼다.
 *
 * @param projectPath 현재 프로젝트 폴더. scratch 세션이면 null이며 이때는 변환하지 않는다.
 * @param value 사용자가 고른 절대 경로. 빈 문자열은 "미지정"이므로 그대로 둔다.
 */
export function toPortablePath(projectPath: string | null, value: string): string {
  if (!value || !projectPath) return value;
  const base = normalizeBase(projectPath);
  if (!base) return value;
  const target = value.replace(/\\/g, "/");
  if (target === base) return PROJECT_PATH_PREFIX;
  if (target.startsWith(`${base}/`)) {
    return PROJECT_PATH_PREFIX + target.slice(base.length + 1);
  }
  return value;
}

/**
 * 스냅샷에 담긴 값을 실제로 열 수 있는 절대 경로로 되돌린다.
 *
 * 접두사가 없으면 구 스냅샷의 절대 경로이므로 그대로 돌려준다. 접두사가 있는데
 * 프로젝트 폴더를 모르면(scratch 등) 되살릴 근거가 없으므로 빈 문자열을 준다.
 * 상대 경로 조각을 그대로 흘리면 백엔드가 엉뚱한 작업 디렉토리 기준으로 해석한다.
 */
export function fromPortablePath(projectPath: string | null, stored: string): string {
  if (!stored || !isPortablePath(stored)) return stored;
  const relative = stored.slice(PROJECT_PATH_PREFIX.length);
  if (!projectPath) return "";
  const base = normalizeBase(projectPath);
  if (!base) return "";
  return relative ? `${base}/${relative}` : base;
}

/**
 * 스냅샷 저장값이 프로젝트 폴더 밖을 가리키는지. 복원 측에서 "옮기면 따라오지
 * 않는 입력"을 가려내는 데 쓴다. 빈 값은 미지정이므로 대상이 아니다.
 */
export function isExternalPath(stored: string): boolean {
  return stored.length > 0 && !isPortablePath(stored);
}
