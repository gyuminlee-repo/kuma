/**
 * §9 Versioning & Updates — updater helper
 *
 * Wraps @tauri-apps/plugin-updater with explicit error classification.
 * All errors surface a human-readable message; none are swallowed silently.
 */

import { check, type Update } from "@tauri-apps/plugin-updater";

export type UpdateCheckResult =
  | { status: "up-to-date"; currentVersion: string }
  | { status: "available"; update: Update; newVersion: string }
  | { status: "not-configured"; message: string }
  | { status: "error"; message: string };

/**
 * Check whether a newer version is available.
 *
 * Classifies errors so callers can show appropriate UI without
 * exposing raw exception strings.
 */
export async function checkForUpdates(): Promise<UpdateCheckResult> {
  try {
    const update = await check();
    if (!update) {
      // plugin returned null — no update available
      return { status: "up-to-date", currentVersion: __APP_VERSION__ };
    }
    return { status: "available", update, newVersion: update.version };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);

    // Empty pubkey / updater not configured produces a recognisable message.
    // Treat configuration errors distinctly so the UI can guide the user.
    if (
      msg.includes("pubkey") ||
      msg.includes("not configured") ||
      msg.includes("No updater endpoints") ||
      msg.includes("invalid key")
    ) {
      return {
        status: "not-configured",
        message:
          "Updater is not configured for this build. See RELEASE_CHECKLIST.md for key generation steps.",
      };
    }

    return { status: "error", message: msg };
  }
}

/**
 * Download and install the given update, then request app restart.
 * Throws on failure — caller is responsible for surfacing the error.
 */
export async function downloadAndInstall(update: Update): Promise<void> {
  await update.downloadAndInstall();
}
