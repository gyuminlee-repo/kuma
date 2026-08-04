import type { PlateOrderSeverity } from "@/types/mame/models";
import type { AppState } from "./types";

/**
 * Whether the stored plate-order finding is worth saying out loud right now.
 *
 * Always "info" when it is: since v0.15.6 the operator picks the sheet and the
 * column the variant list is read from, so the program has no standing to call
 * a disagreement between two sheets of one workbook an error. It reports what
 * it saw and leaves the reading to the person who chose it.
 *
 * null = nothing to say. That covers no finding at all, and the case where the
 * operator named the sheet and column themselves: they already stated which
 * rows to read, and repeating "these two sheets differ" back at them adds
 * nothing they did not just decide.
 */
export function selectPlateOrderSeverity(s: AppState): PlateOrderSeverity | null {
  if (!s.plateOrderFinding) return null;
  if (s.variantSelectionExplicit) return null;
  return "info";
}

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
  // A plate-order disagreement no longer appears here. It is stated on the
  // inputs panel and the run proceeds; see selectPlateOrderSeverity.
  return (
    pathsReady &&
    !s.isAnalyzing &&
    !s.isValidating &&
    s.validationErrors.length === 0
  );
}
