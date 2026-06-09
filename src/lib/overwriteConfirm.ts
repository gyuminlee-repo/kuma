/**
 * §5 Output Persistence — 덮어쓰기 confirm 유틸.
 *
 * export 핸들러가 저장 경로를 확보한 직후 호출.
 * 파일이 이미 존재하면 shadcn AlertDialog(또는 표준 Dialog)를 통해
 * "Overwrite" / "Cancel" 중 하나를 반환한다.
 *
 * 파일 존재 여부 확인은 `@tauri-apps/plugin-fs`의 `exists()`를 사용.
 * Dialog 표시는 Tauri 내장 `ask()` (네이티브 다이얼로그) 대신
 * 앱 레벨 Promise 기반 resolve 패턴으로 구현해 shadcn 스타일을 유지한다.
 */

import { exists } from "@tauri-apps/plugin-fs";

/**
 * 파일이 이미 존재하면 true를 반환한다.
 *
 * exists() 실패(권한 오류, Tauri fs scope 밖 경로 등) 시 보수적으로 true를 반환해
 * 덮어쓰기 confirm이 건너뛰어지는 위험을 막는다.
 * 사용자가 파일 위치를 확인할 수 없는 상황에서는 confirm이 뜨는 것이 안전하다.
 */
export async function fileExists(filepath: string): Promise<boolean> {
  try {
    return await exists(filepath);
  } catch (err) {
    // Tauri fs scope 밖 경로, 권한 오류 등 — fail-safe로 true 반환.
    // confirm 다이얼로그가 불필요하게 뜰 수 있지만, 조용히 덮어쓰는 것보다 안전하다.
    console.warn("[overwriteConfirm] fileExists failed, assuming file exists:", err);
    return true;
  }
}

/** 덮어쓰기 confirm 결과 */
export type OverwriteDecision = "overwrite" | "cancel";

/**
 * AlertDialog를 열고 사용자 결정을 Promise로 반환한다.
 *
 * 이 함수는 전역 `overwriteConfirmStore`를 통해 React 트리 외부에서
 * AlertDialog를 제어하는 방식을 사용한다.
 *
 * 호출자:
 *   const decision = await requestOverwriteConfirm(path);
 *   if (decision === "cancel") return;
 *   // proceed with export
 */

type ResolveCallback = (decision: OverwriteDecision) => void;

let _pendingResolve: ResolveCallback | null = null;
let _pendingPath: string | null = null;
let _pendingMessage: string | null = null;
let _listener: (() => void) | null = null;

/** OverwriteConfirmDialog 컴포넌트가 상태 변화를 감지하기 위해 등록하는 리스너 */
export function subscribeOverwriteConfirm(callback: () => void): () => void {
  _listener = callback;
  return () => {
    _listener = null;
  };
}

/** 현재 대기 중인 confirm 요청 경로 (없으면 null) */
export function getPendingOverwritePath(): string | null {
  return _pendingPath;
}

/**
 * 현재 대기 중인 confirm 의 커스텀 메시지 (없으면 null).
 *
 * 디렉터리 단위 confirm 처럼 파일명+기본 문구로 표현할 수 없는 경우,
 * 호출자가 이미 번역한 전체 문장을 전달한다. null 이면 다이얼로그는
 * 기존 파일명 + 기본 description 렌더링을 사용한다.
 */
export function getPendingOverwriteMessage(): string | null {
  return _pendingMessage;
}

/**
 * 덮어쓰기 여부를 사용자에게 확인한다.
 *
 * @param filepath - 덮어쓸 대상 파일(또는 디렉터리)의 절대 경로
 * @param message - (선택) 이미 번역된 커스텀 메시지. 전달 시 파일명+기본 문구 대신 표시.
 * @returns "overwrite" | "cancel"
 */
export function requestOverwriteConfirm(
  filepath: string,
  message?: string,
): Promise<OverwriteDecision> {
  return new Promise<OverwriteDecision>((resolve) => {
    _pendingPath = filepath;
    _pendingMessage = message ?? null;
    _pendingResolve = resolve;
    _listener?.();
  });
}

/** OverwriteConfirmDialog 내부에서 사용자 선택을 전달한다 */
export function resolveOverwriteConfirm(decision: OverwriteDecision): void {
  const resolve = _pendingResolve;
  _pendingPath = null;
  _pendingMessage = null;
  _pendingResolve = null;
  resolve?.(decision);
  _listener?.();
}
