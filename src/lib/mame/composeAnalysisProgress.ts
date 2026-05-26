export type AnalysisPhase = "sort" | "analyze";
export type IngestMode = "raw_run" | "barcode";

export function composeAnalysisProgress(
  rawPct: number,
  phase: AnalysisPhase,
  ingestMode: IngestMode = "raw_run",
): number {
  if (phase === "sort") return Math.round(rawPct * 0.5);
  if (ingestMode === "raw_run") return Math.round(50 + rawPct * 0.5);
  return Math.round(rawPct);
}
