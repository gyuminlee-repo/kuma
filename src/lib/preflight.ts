/**
 * §19 Performance Guardrails — Run pre-flight check helper
 *
 * Checks: sidecar alive, disk space (best-effort), network reachability.
 * Each failed check appends to errors (ok:false) or warnings (ok:true with caveats).
 */

import i18next from "i18next";

export interface PreflightResult {
  ok: boolean;
  warnings: string[];
  errors: string[];
}

export interface PreflightOpts {
  /** Sidecar status string from useSidecar() / useMameSidecar(). */
  sidecarStatus: "disconnected" | "connecting" | "ready" | "error";
  /** Estimated output size in bytes — reserved for future disk-space comparison. */
  estimatedOutputBytes?: number;
  /** Whether the run requires external network access (e.g. UniProt/BLAST). */
  requiresNetwork?: boolean;
}

export async function runPreflightCheck(
  opts: PreflightOpts,
): Promise<PreflightResult> {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 1. Sidecar alive
  if (opts.sidecarStatus !== "ready") {
    errors.push(
      i18next.t("preflight.errSidecarNotReady", { status: opts.sidecarStatus }),
    );
  }

  // 2. Disk free space — no cross-platform Tauri v2 API available.
  //    navigator.storage.estimate() returns origin quota, not actual disk free,
  //    so it is intentionally skipped to avoid misleading numbers.
  warnings.push(
    i18next.t("preflight.warnDiskUnavailable"),
  );

  // 3. Network reachability (only when requiresNetwork is true)
  if (opts.requiresNetwork) {
    if (!navigator.onLine) {
      errors.push(
        i18next.t("preflight.errNoNetwork"),
      );
    }
  }

  return {
    ok: errors.length === 0,
    warnings,
    errors,
  };
}
