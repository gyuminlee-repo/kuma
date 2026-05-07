/**
 * §13 OS native notification helper.
 *
 * Wraps tauri-plugin-notification with:
 * - Threshold guard: skip notifications for jobs shorter than `thresholdMs` (default 5 min)
 * - Permission flow: isPermissionGranted → requestPermission → sendNotification
 * - Silent fail: permission denial or API errors do not throw
 */

import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from "@tauri-apps/plugin-notification";

/** Default threshold: 5 minutes in milliseconds */
const DEFAULT_THRESHOLD_MS = 5 * 60 * 1000;

export interface NotifyJobCompleteOptions {
  /** Notification title */
  title: string;
  /** Notification body */
  body: string;
  /**
   * Minimum elapsed time (ms) before a notification fires.
   * Jobs shorter than this threshold are silently skipped.
   * Default: 300_000 (5 minutes).
   */
  thresholdMs?: number;
  /** `Date.now()` captured before the job started */
  startedAt: number;
}

/**
 * Send an OS native notification for a completed long-running job.
 *
 * Silently returns without throwing if:
 * - The job elapsed time is below `thresholdMs`
 * - The user denied notification permission
 * - The notification API is unavailable
 */
export async function notifyJobComplete(
  opts: NotifyJobCompleteOptions,
): Promise<void> {
  const { title, body, thresholdMs = DEFAULT_THRESHOLD_MS, startedAt } = opts;

  // Threshold guard — skip notifications for short jobs.
  if (Date.now() - startedAt < thresholdMs) {
    return;
  }

  try {
    let granted = await isPermissionGranted();
    if (!granted) {
      const permission = await requestPermission();
      granted = permission === "granted";
    }
    if (!granted) {
      // User denied — silent fail (no throw, no console.error spam).
      return;
    }
    sendNotification({ title, body });
  } catch {
    // Notification API unavailable or runtime error — silent fail.
    // The in-app statusMessage already reflects job completion.
  }
}

/**
 * Check whether OS notification permission has been granted.
 *
 * Returns false if the API is unavailable.
 */
export async function notificationPermissionGranted(): Promise<boolean> {
  try {
    return await isPermissionGranted();
  } catch {
    return false;
  }
}

/**
 * Request OS notification permission.
 *
 * Returns false if already denied or API unavailable.
 */
export async function requestNotificationPermission(): Promise<boolean> {
  try {
    const permission = await requestPermission();
    return permission === "granted";
  } catch {
    return false;
  }
}
