/**
 * §8 In-app toast notification helpers.
 *
 * Wraps Sonner to provide a consistent toast API for completed/failed jobs.
 * Always fires (no threshold guard) — use in addition to notify.ts (OS notifications).
 */

import { toast } from "sonner";

/** Format elapsed milliseconds as human-readable string. */
function formatDuration(ms: number): string {
  if (ms < 1_000) {
    return `${ms}ms`;
  }
  const totalSeconds = Math.round(ms / 1_000);
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

export interface NotifyJobDoneOptions {
  /** Toast title */
  title: string;
  /** Optional description override. Defaults to elapsed time. */
  description?: string;
  /** Elapsed time in milliseconds (shown in description if no override). */
  durationMs: number;
}

/**
 * Show a success toast for a completed job.
 * Always fires regardless of elapsed time.
 */
export function notifyJobDone(opts: NotifyJobDoneOptions): void {
  toast.success(opts.title, {
    description: opts.description ?? `완료 (${formatDuration(opts.durationMs)})`,
    duration: 4000,
  });
}

/**
 * Show an error toast for a failed job.
 */
export function notifyJobError(title: string, error: unknown): void {
  toast.error(title, {
    description: String(error),
    duration: 6000,
  });
}
