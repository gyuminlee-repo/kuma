/**
 * pathRef.ts, 자동 저장 스냅샷에 담는 파일 경로 표현
 *
 * 스냅샷은 지금까지 사용자가 파일 다이얼로그로 고른 **절대 경로**를 그대로
 * 담았다. 프로젝트 폴더를 옮기거나 다른 PC 에서 열면 그 경로가 전부 죽는다.
 * 매니페스트(`lib/workspace/api.ts`)는 이미 상대 경로로 적고 있었으므로,
 * 스냅샷만 뒤처져 있던 셈이다.
 *
 * 여기서는 경로를 두 종류로 나눈다.
 *
 *   project  프로젝트 폴더 안. 상대 경로로 적는다. 폴더를 통째로 복사하면
 *            재탐색 없이 그대로 열린다.
 *   external 프로젝트 폴더 밖. raw MinKNOW run 폴더(수 GB)처럼 프로젝트에
 *            담을 수 없는 원천 입력이 여기 들어온다. 절대 경로에 더해 이름과
 *            크기·수정시각을 함께 적어, 받는 쪽에서 다시 지정할 때 같은
 *            파일인지 대조할 수 있게 한다.
 *
 * 읽기는 구버전 스냅샷과 호환된다. 문자열이 오면 절대 경로로 간주한다.
 * store 를 import 하지 않는 순수 모듈로 유지한다(`kuroResultReset.ts` 선례).
 */

/** 프로젝트 폴더 기준 상대 경로. 구분자는 항상 슬래시로 정규화한다. */
export interface ProjectPathRef {
  kind: "project";
  rel: string;
}

/**
 * 프로젝트 폴더 밖의 원천 입력.
 *
 * `size`/`mtime` 은 재지정한 파일이 원래 것과 같은지 확인하는 용도다. 수집에
 * 실패했으면 생략한다(없다고 참조가 무효가 되지는 않는다).
 */
export interface ExternalPathRef {
  kind: "external";
  path: string;
  name: string;
  size?: number;
  mtime?: string;
}

export type PathRef = ProjectPathRef | ExternalPathRef;

/** 스냅샷에서 읽어 들이는 값. 구버전은 맨 문자열이었다. */
export type StoredPath = PathRef | string | null | undefined;

function normalise(p: string): string {
  return p.replace(/\\/g, "/");
}

function stripTrailingSlash(p: string): string {
  return p.replace(/\/+$/, "");
}

/** 경로에서 파일(또는 폴더) 이름만. 사용자 안내 문구에 쓴다. */
export function baseName(filePath: string): string {
  const parts = stripTrailingSlash(normalise(filePath)).split("/");
  return parts[parts.length - 1] || filePath;
}

/**
 * 절대 경로를 스냅샷에 적을 형태로 바꾼다.
 *
 * 프로젝트 폴더 자체(`absolute === projectPath`)는 상대 경로가 빈 문자열이 되어
 * 복원 때 폴더인지 파일인지 구분이 안 되므로 external 로 둔다. 실사용에서
 * 입력이 프로젝트 루트 그 자체인 경우는 드물지만, 빈 rel 이 조용히 잘못 복원되는
 * 것보다 낫다.
 *
 * @param projectPath 활성 프로젝트 폴더. 없으면(스크래치) 전부 external 이다.
 * @param absolute    사용자가 고른 절대 경로.
 * @param stat        선택. external 참조에 붙일 크기·수정시각.
 */
export function toPathRef(
  projectPath: string | null | undefined,
  absolute: string,
  stat?: { size?: number; mtime?: string },
): PathRef {
  const name = baseName(absolute);
  if (!projectPath) {
    return { kind: "external", path: absolute, name, ...stat };
  }
  const base = stripTrailingSlash(normalise(projectPath));
  const target = normalise(absolute);
  if (target.startsWith(base + "/")) {
    return { kind: "project", rel: target.slice(base.length + 1) };
  }
  return { kind: "external", path: absolute, name, ...stat };
}

/**
 * 스냅샷에서 읽은 값을 현재 환경의 절대 경로로 되돌린다.
 *
 * 구버전 스냅샷(맨 문자열)은 그대로 돌려준다. 그 값이 살아 있는지는 호출부가
 * 존재 검사로 판단한다(`lib/mame/stalePaths.ts`).
 *
 * @returns 절대 경로. 복원할 수 없으면 빈 문자열.
 */
export function fromPathRef(
  projectPath: string | null | undefined,
  stored: StoredPath,
): string {
  if (!stored) return "";
  if (typeof stored === "string") return stored;
  if (stored.kind === "external") return stored.path;
  if (!projectPath) return "";
  const base = stripTrailingSlash(normalise(projectPath));
  return stored.rel ? `${base}/${stored.rel}` : "";
}

/** 저장된 값이 프로젝트 밖 참조면 그 참조를, 아니면 null. */
export function asExternalRef(stored: StoredPath): ExternalPathRef | null {
  if (!stored || typeof stored === "string") return null;
  return stored.kind === "external" ? stored : null;
}
