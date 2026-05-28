import type { AppState } from "./types";

export function selectCanRun(s: AppState): boolean {
  let pathsReady: boolean;
  if (s.inputMode === "raw_run") {
    // Combinatorial demux: needs inputDir + customBarcodesPath + referencePath + outputPath.
    // expectedPath (KURO xlsx) is optional, provided via kuro_xlsx param when available.
    pathsReady = Boolean(
      s.inputDir &&
      s.rawRunParams.customBarcodesPath &&
      s.referencePath &&
      s.outputPath,
    );
  } else {
    pathsReady = Boolean(s.inputDir && s.expectedPath && s.referencePath && s.outputPath);
  }
  return (
    pathsReady &&
    !s.isAnalyzing &&
    !s.isValidating &&
    s.validationErrors.length === 0
  );
}
