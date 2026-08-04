import { gradePlateOrder } from "@/lib/mame/plateOrderMessage";
import type { PlateOrderSeverity } from "@/types/mame/models";
import type { AppState } from "./types";

/**
 * How much the stored plate-order finding costs the run as it stands now.
 *
 * The sidecar graded the finding against the layout inputs it was sent, and the
 * operator can change those inputs afterwards (pick a sample map, confirm a well
 * layout). Re-grading here keeps the gate honest without a second round-trip,
 * and applies the same rule as `_plate_order_finding` in
 * `python-core/sidecar_mame/handlers/analyze.py`.
 *
 * null = no finding, i.e. nothing to say and nothing to stop.
 */
export function selectPlateOrderSeverity(s: AppState): PlateOrderSeverity | null {
  const finding = s.plateOrderFinding;
  if (!finding) return null;
  return gradePlateOrder(finding, {
    hasSampleMap: Boolean(s.sampleMapPath),
    hasWellLayout: s.wellLayout !== null,
  });
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
  return (
    pathsReady &&
    !s.isAnalyzing &&
    !s.isValidating &&
    s.validationErrors.length === 0 &&
    // The backend leaves `valid` true for a plate disagreement so `valid` keeps
    // its old meaning, which makes this gate the frontend's job. Running an
    // inferred layout off two disagreeing sheets scores every well against a
    // design nobody built, and nothing in the output says so.
    selectPlateOrderSeverity(s) !== "blocking"
  );
}
