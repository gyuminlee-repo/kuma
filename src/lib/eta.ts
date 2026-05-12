/**
 * §2 Observability — ETA (Estimated Time Remaining) helper.
 *
 * Tracks per-jobKind run durations in localStorage and provides
 * remaining-time estimates based on the rolling average.
 *
 * Storage key: `kuma:eta-history:{kind}` → JSON array of last N durationMs values.
 */

import i18next from "i18next";

const HISTORY_KEY_PREFIX = "kuma:eta-history:";
const MAX_HISTORY = 10;

/**
 * Record a completed run's duration for future ETA estimation.
 *
 * @param jobKind   Job category (matches JobKind in jobQueueSlice)
 * @param durationMs  Elapsed milliseconds for the completed job
 */
export function recordRunDuration(jobKind: string, durationMs: number): void {
  if (durationMs <= 0) return;
  const key = `${HISTORY_KEY_PREFIX}${jobKind}`;
  try {
    const raw = localStorage.getItem(key);
    const history: number[] = raw !== null ? (JSON.parse(raw) as number[]) : [];
    history.push(durationMs);
    while (history.length > MAX_HISTORY) {
      history.shift();
    }
    localStorage.setItem(key, JSON.stringify(history));
  } catch {
    // localStorage unavailable — silently ignore
  }
}

/**
 * Estimate remaining time based on historical averages.
 *
 * @param jobKind        Job category
 * @param currentProgress  0–100 progress percentage
 * @returns Estimated remaining milliseconds, or null if no history
 */
export function estimateETA(
  jobKind: string,
  currentProgress: number,
): number | null {
  if (currentProgress <= 0 || currentProgress >= 100) return null;
  const key = `${HISTORY_KEY_PREFIX}${jobKind}`;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const history: number[] = JSON.parse(raw) as number[];
    if (history.length === 0) return null;
    const avg = history.reduce((a, b) => a + b, 0) / history.length;
    // Estimate total time from current progress, then subtract elapsed portion
    const estimatedTotal = avg;
    const remaining = estimatedTotal * (1 - currentProgress / 100);
    return remaining > 0 ? remaining : null;
  } catch {
    return null;
  }
}

/**
 * Format a remaining-time value into a human-readable Korean string.
 *
 * @param ms  Remaining milliseconds
 * @returns   e.g. "약 2분 30초 남음" or "약 45초 남음"
 */
export function formatETA(ms: number): string {
  const totalSec = Math.ceil(ms / 1000);
  if (totalSec <= 0) return "";
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min === 0) return i18next.t("eta.secOnly", { sec });
  if (sec === 0) return i18next.t("eta.minOnly", { min });
  return i18next.t("eta.minSec", { min, sec });
}

/**
 * Clear ETA history for a specific kind (useful for testing or reset).
 */
export function clearETAHistory(jobKind: string): void {
  try {
    localStorage.removeItem(`${HISTORY_KEY_PREFIX}${jobKind}`);
  } catch {
    // ignore
  }
}
