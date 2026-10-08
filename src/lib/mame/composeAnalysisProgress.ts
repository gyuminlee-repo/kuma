export type AnalysisPhase = "demux" | "analyze";

/**
 * Maps raw RPC progress (0-100) to a unified monotonic 0-100 scale.
 *
 * Monotonicity guarantee (construction-based, no Math.max guard needed):
 *  - raw_run: phase "demux" → [0, 50], phase "analyze" → [50, 100].
 *    analyzePhase only advances demux→analyze, never back.
 *    The handoff (demux 100→50, analyze 0→50) is contiguous at 50.
 *  - sorted/barcode (isRawRun=false): phase is always "analyze" → [0, 100].
 */
export function composeAnalysisProgress(
  rawPct: number,
  phase: AnalysisPhase,
  isRawRun: boolean,
): number {
  const clamped = Math.max(0, Math.min(100, rawPct));
  if (!isRawRun) return Math.round(clamped);
  if (phase === "demux") return Math.round(clamped * 0.5);
  return Math.round(50 + clamped * 0.5);
}
