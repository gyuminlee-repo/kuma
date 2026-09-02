/**
 * TypeScript mirror of the `mame.activity.detect_measurement_source` RPC.
 *
 * Hand-written, like every other file in this directory: `pnpm gen:models`
 * generates `src/types/models.generated.ts` from `sidecar_kuro.models` only
 * (`.cross-layer-sync.json` `genModels`), so the MAME contracts are mirrored by
 * hand. Source of truth is `python-core/sidecar_mame/models.py`
 * (`DetectMeasurementSourceParams`, `DetectMeasurementSourceResult`).
 */

/** The four step 4.1 measurement sources, plus the long format they share. */
export type MeasurementSource =
  | "longFormat"
  | "gcSheet"
  | "rawReport"
  | "numericReport"
  | "confirmationVariantLabels";

export const MEASUREMENT_SOURCES: readonly MeasurementSource[] = [
  "longFormat",
  "gcSheet",
  "rawReport",
  "numericReport",
  "confirmationVariantLabels",
];

export interface DetectMeasurementSourceParams {
  /** The measurement file to read. `.csv`, `.xlsx`, or `.xls`. */
  measurement_path: string;
  /** Zero-based sheet index for a workbook. Ignored for a csv. */
  sheet_index?: number;
}

export interface DetectMeasurementSourceResult {
  /** The file that was read, resolved. */
  path: string;
  /**
   * Every source the file could be, never narrowed to a guess. A
   * pre-normalized GC sheet is also a valid long-format file, and the two
   * readings differ in what they do with the wild-type rows, so both are
   * reported and the operator chooses. An empty list is an answer: the file is
   * none of the four, and `reason` says what was seen.
   */
  candidates: MeasurementSource[];
  /** `candidates.length > 1`. */
  ambiguous: boolean;
  /**
   * What the detector saw: the header it echoed, whether the FID1B block
   * signature was present, the sample-name namespaces it counted and a few
   * examples of each, and the row counts. Shown so an operator can tell why a
   * file was classified as it was, so the shape is deliberately open.
   */
  evidence: Record<string, unknown>;
  /** Empty when `candidates` is non-empty; otherwise why the file matched nothing. */
  reason: string;
}
