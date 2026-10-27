/**
 * TypeScript mirror of the `mame.activity.detect_measurement_source` RPC.
 *
 * Hand-written, like every other file in this directory: `pnpm gen:models`
 * generates `src/types/models.generated.ts` from `sidecar_kuro.models` only
 * (`.cross-layer-sync.json` `genModels`), so the MAME contracts are mirrored by
 * hand. Source of truth is `python-core/sidecar_mame/models.py`
 * (`DetectMeasurementSourceParams`, `DetectMeasurementSourceResult`).
 */

/**
 * The step 4.1 measurement sources. Mirrors `MEASUREMENT_SOURCES` in
 * `kuma_core/mame/activity/detect_measurement_source.py`; the two lists must
 * hold the same names.
 */
export type MeasurementSource =
  | "longFormat"
  | "gcSheet"
  | "rawReport"
  | "numericReport"
  | "confirmationWellLabels"
  | "confirmationVariantLabels"
  | "confirmationNumericIds";

export const MEASUREMENT_SOURCES: readonly MeasurementSource[] = [
  "longFormat",
  "gcSheet",
  "rawReport",
  "numericReport",
  "confirmationWellLabels",
  "confirmationVariantLabels",
  "confirmationNumericIds",
];

export interface DetectMeasurementSourceParams {
  /** The measurement file to read. `.csv`, `.xlsx`, or `.xls`. */
  measurement_path: string;
  /** Zero-based sheet index for a workbook. Ignored for a csv. */
  sheet_index?: number;
  /**
   * The field the file was chosen for. `"confirmation"` reports one of the
   * three confirmation sources or nothing, one candidate per sample-name
   * namespace: a well-labeled report is `confirmationWellLabels` alone and a
   * numeric-ID report `confirmationNumericIds` alone. Defaults to `"primary"`,
   * where a well-labeled report is `rawReport` alone.
   */
  slot?: "primary" | "confirmation";
}

export interface DetectMeasurementSourceResult {
  /** The file that was read, resolved. */
  path: string;
  /**
   * Every source the file could be, never narrowed to a guess. Two pairs are
   * the same file in the primary slot: a pre-normalized GC sheet is also a valid
   * long-format file, and a numeric-ID block file is a primary screen or a
   * numeric confirmation because both decoders call the same parser. A file
   * whose names fit several label grammars lists one candidate per grammar.
   * Any block file may carry sample names of no namespace (BLANK, internal
   * standards, another experiment's samples); they never block a reading,
   * `evidence.sample_name_namespaces.unclassified` counts them, and the build
   * sets them aside with their positions. Each reading is reported whole and
   * the operator chooses. An empty list is an answer: the file is none of
   * them, and `reason` says what was seen.
   */
  candidates: MeasurementSource[];
  /** `candidates.length > 1`. */
  ambiguous: boolean;
  /**
   * What the detector saw: the header it echoed, whether the FID1B block
   * signature was present, well_columns/label_columns/value_columns (arrays
   * of recognized normalized headers; a dual-column sheet uses Sample as the
   * label and checks well identities against mapping evidence at build time),
   * the sample-name namespaces it counted and a few
   * examples of each, and optional counts: n_sample_rows (non-WT samples),
   * n_recognized_rows (syntactically recognized non-WT labels), n_control_rows
   * (WT controls used for normalization), n_skipped_rows (names of no
   * namespace the build will set aside, present only when there are any), and n_unique_labels. These are observations, not NGS-qualified variant counts. Consumers must validate
   * numeric values at runtime and must not substitute zero for a missing count.
   * The shape stays open so operators can see the evidence for classification.
   */
  evidence: Record<string, unknown>;
  /** Empty when `candidates` is non-empty; otherwise why the file matched nothing. */
  reason: string;
}
