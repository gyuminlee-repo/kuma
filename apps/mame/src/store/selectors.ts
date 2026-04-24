import type { AppState } from "./types";

export function selectCanRun(s: AppState): boolean {
  const pathsReady = Boolean(s.inputDir && s.expectedPath && s.referencePath && s.outputPath);
  return (
    pathsReady &&
    !s.isAnalyzing &&
    !s.isValidating &&
    s.validationErrors.length === 0
  );
}
