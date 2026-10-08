/**
 * §22 Graceful Shutdown — 종료 직전 실행 훅 레지스트리.
 *
 * MainShell.tsx 의 onCloseRequested 에서 runShutdownHooks() 를 호출한다.
 * 각 훅은 best-effort 로 실행되며, 개별 훅의 오류가 전체 종료를 막지 않는다.
 */

type Hook = () => Promise<void> | void;

const _hooks: Set<Hook> = new Set();

/**
 * 종료 훅을 등록한다.
 *
 * @returns unregister 함수 (useEffect cleanup 으로 사용).
 *
 * @example
 * ```ts
 * useEffect(() => {
 *   return registerShutdownHook(async () => {
 *     await flushPendingData();
 *   });
 * }, []);
 * ```
 */
export function registerShutdownHook(hook: Hook): () => void {
  _hooks.add(hook);
  return () => {
    _hooks.delete(hook);
  };
}

/**
 * 등록된 모든 종료 훅을 순서대로 실행한다.
 * 개별 훅 오류는 console.warn 으로 기록하고 계속 진행한다.
 */
export async function runShutdownHooks(): Promise<void> {
  for (const hook of _hooks) {
    try {
      await hook();
    } catch (err) {
      // 종료 경로에서 훅 오류는 치명적이지 않음. 경고만 기록.
      console.warn("[shutdownHook] hook error during shutdown:", err);
    }
  }
}
