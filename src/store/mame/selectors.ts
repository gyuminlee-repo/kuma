import type { AppState } from "./types";

export function selectCanRun(s: AppState): boolean {
  const pathsReady = Boolean(s.inputDir && s.expectedPath && s.referencePath && s.outputPath);
  const rawRunReady =
    s.inputMode !== "raw_run" || Boolean(s.rawRunParams.customBarcodesPath);
  return (
    pathsReady &&
    rawRunReady &&
    !s.isAnalyzing &&
    !s.isValidating &&
    s.validationErrors.length === 0
  );
}
