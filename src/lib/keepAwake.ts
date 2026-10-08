import { invoke } from "@tauri-apps/api/core";

/**
 * §13 Sleep inhibit: prevent OS from sleeping during long-running jobs.
 *
 * Per task spec: OS permission denial is non-fatal — warn and continue.
 * Justification for silent-continue: keepawake failure does not affect
 * correctness of the job; the OS may legitimately deny inhibit (sandboxed
 * environments, policy restrictions). Logging is preserved via console.warn.
 * ANTIFALLBACK_OVERRIDE reason: task owner explicitly specified "warn only, no rethrow".
 */

export async function startKeepAwake(reason: string): Promise<void> {
  try {
    await invoke<void>("keep_awake_start", { reason });
  } catch (err) {
    // Non-fatal: OS may deny sleep inhibit (sandbox, policy).
    // Job continues normally; user is not blocked.
    console.warn("[keepAwake] OS sleep inhibit unavailable:", err);
  }
}

export async function stopKeepAwake(): Promise<void> {
  try {
    await invoke<void>("keep_awake_stop");
  } catch (err) {
    console.warn("[keepAwake] Failed to release sleep inhibit:", err);
  }
}
