/**
 * §1 Recovery — Dead-lock 감지 유틸리티.
 *
 * progress notification 이 thresholdMs(기본 30초) 이상 끊기면 onDeadlock 콜백을 호출.
 * 호출부는 getLastProgressAt 으로 최신 progress timestamp 를 제공하고,
 * 반환된 cleanup 함수를 useEffect 반환값으로 연결해야 한다.
 */

export const DEADLOCK_THRESHOLD_MS = 30_000;

export interface DeadlockWatchOptions {
  /** 마지막 progress 수신 timestamp(ms) 반환. progress 없으면 null. */
  getLastProgressAt: () => number | null;
  /** 감지 판정 임계값(ms). 기본값: DEADLOCK_THRESHOLD_MS(30초). */
  thresholdMs?: number;
  /** 데드락 감지 시 1회 호출되는 콜백. */
  onDeadlock: () => void;
}

/**
 * Dead-lock watch 를 시작한다.
 *
 * @returns cleanup 함수 (타이머 해제). useEffect 반환값으로 사용.
 *
 * @example
 * ```ts
 * useEffect(() => {
 *   if (!isDesigning) return;
 *   return startDeadlockWatch({
 *     getLastProgressAt: () => lastProgressAtRef.current,
 *     onDeadlock: () => setDeadlockOpen(true),
 *   });
 * }, [isDesigning]);
 * ```
 */
export function startDeadlockWatch(opts: DeadlockWatchOptions): () => void {
  const { getLastProgressAt, thresholdMs = DEADLOCK_THRESHOLD_MS, onDeadlock } = opts;

  // 감지 시작 시각 기록 (최초 progress 수신 전 임계값 판정 방지)
  const watchStartedAt = Date.now();
  let fired = false;

  const id = setInterval(() => {
    if (fired) return;

    const lastAt = getLastProgressAt();
    const now = Date.now();

    if (lastAt === null) {
      // progress 를 아직 한 번도 받지 못했다면 watch 시작 후 thresholdMs 경과 시 판정
      if (now - watchStartedAt >= thresholdMs) {
        fired = true;
        onDeadlock();
      }
      return;
    }

    if (now - lastAt >= thresholdMs) {
      fired = true;
      onDeadlock();
    }
  }, 5_000); // 5초 폴링

  return () => clearInterval(id);
}
