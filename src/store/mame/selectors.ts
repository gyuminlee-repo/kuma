import type { PlateOrderSeverity } from "@/types/mame/models";
import type { AppState } from "./types";

/**
 * Whether the stored plate-order finding is worth saying out loud right now.
 *
 * Always "blocking" when there is one. A workbook whose primer plate sheet and
 * `expected_mutations` describe different plates does not record which of the two
 * was pipetted, and nothing on this screen can supply that: a sample map or a
 * confirmed layout places wells, it does not certify which plate the tubes came
 * from. So the finding is stated as a refusal and the run waits for a workbook
 * whose sheets agree.
 *
 * It graded itself "info" between v0.15.6 and 2026-08-05 whenever a sample map
 * or a well layout supplied the coordinates, on the reasoning that the sheet
 * order never reached a well. True of the wells, false of the run: the verdicts
 * were still scored against whichever of the two plates the other input happened
 * to match, unchecked.
 *
 * null = no finding. The `variantSelectionExplicit` exemption is gone with the
 * grading: `handle_validate_inputs` now errors on the disagreement whatever the
 * operator named, and a notice that hid itself while validation failed left the
 * failure unexplained.
 */
export function selectPlateOrderSeverity(s: AppState): PlateOrderSeverity | null {
  return s.plateOrderFinding ? "blocking" : null;
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
  // A plate-order disagreement stops the run. `validate_inputs` reports it as an
  // error too, so most of the time `validationErrors` would already be holding
  // the button; this covers the window that error does not reach, which is where
  // the 2026-08-04 incident lived: picking the workbook runs `check_plate_order`
  // on its own, and the operator can press Run without ever validating.
  //
  // Cleared by picking another expected workbook (`setExpectedPath` drops the
  // finding, and the re-check writes one back only if the new file disagrees
  // with itself too). Nothing else clears it, by design: which sheet was
  // pipetted is recorded in no input on this screen.
  return (
    pathsReady &&
    !s.isAnalyzing &&
    !s.isValidating &&
    s.validationErrors.length === 0 &&
    s.plateOrderFinding === null
  );
}
