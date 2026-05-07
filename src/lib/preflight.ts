/**
 * §19 Performance Guardrails — Run pre-flight check helper
 *
 * Checks: sidecar alive, disk space (best-effort), network reachability.
 * Each failed check appends to errors (ok:false) or warnings (ok:true with caveats).
 */

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
      `Sidecar is not ready (status: ${opts.sidecarStatus}). Restart the app or use the Retry button in the status bar.`,
    );
  }

  // 2. Disk free space — no cross-platform Tauri v2 API available.
  //    navigator.storage.estimate() returns origin quota, not actual disk free,
  //    so it is intentionally skipped to avoid misleading numbers.
  warnings.push(
    "Disk space check is unavailable on this platform. Ensure sufficient free space before running.",
  );

  // 3. Network reachability (only when requiresNetwork is true)
  if (opts.requiresNetwork) {
    if (!navigator.onLine) {
      errors.push(
        "No network connection detected. This run requires internet access (e.g. UniProt/BLAST).",
      );
    }
  }

  return {
    ok: errors.length === 0,
    warnings,
    errors,
  };
}
