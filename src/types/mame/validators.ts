/**
 * Runtime shape guards for MAME JSON-RPC results.
 *
 * The KURO client has validated its side since `getRpcResultValidator` landed
 * (`src/types/validators.ts`): a payload that does not match the declared result
 * type is refused rather than cast. The MAME client cast straight to `T`, so
 * every number a MAME handler returns reached the UI on the strength of a type
 * annotation and nothing else, and a handler that changed shape (or a sidecar of
 * a different build answering) produced `undefined` deep inside a component
 * instead of an error at the boundary.
 *
 * The check belongs to the client, not to the callers: `sendRequest` in
 * `src/lib/ipc-mame/index.ts` looks a validator up for every method it sends, so
 * a method added later is covered by whatever this table says about it rather
 * than by whoever remembers to guard the call.
 *
 * COVERAGE IS PARTIAL AND THE GAP IS NAMED. `MAME_UNVALIDATED_METHODS` lists
 * every dispatcher method with no entry here; see its comment for why each group
 * is still open. A method in neither list is a method nobody has classified, and
 * `assertKnownMameMethod` in the test suite is what keeps that from happening
 * quietly.
 *
 * Numbers are checked with `Number.isFinite`, matching the KURO guards: `NaN`
 * and `Infinity` are what a broken numeric pipeline produces, and they pass
 * `typeof x === "number"`.
 */

import { isRecord } from "../validators";

/** A guard over one method result. Returns false when the payload is refused. */
export type MameResultValidator = (value: unknown) => boolean;

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isFiniteNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(isFiniteNumber);
}

function isRecordOfString(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(isString);
}

function isRecordOfFiniteNumber(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(isFiniteNumber);
}

function isNullableFiniteNumber(value: unknown): boolean {
  return value === null || isFiniteNumber(value);
}

function isMismatchedVariant(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.variant) &&
    isFiniteNumber(value.authoritative) &&
    isFiniteNumber(value.fallback)
  );
}

function isLabelFinding(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.well) &&
    isString(value.expected) &&
    isStringArray(value.observed) &&
    isString(value.category) &&
    isString(value.verdict)
  );
}

function isLabelAudit(value: unknown): boolean {
  if (value === null) return true;
  return (
    isRecord(value) &&
    Array.isArray(value.discordant) &&
    value.discordant.every(isLabelFinding) &&
    isFiniteNumber(value.n_checked) &&
    isFiniteNumber(value.n_unevaluable) &&
    typeof value.is_closed_permutation === "boolean" &&
    Array.isArray(value.cycles) &&
    value.cycles.every(isStringArray) &&
    (value.geometry === null || isString(value.geometry))
  );
}

/**
 * `mame.activity.build_evolvepro_input`.
 *
 * `wt_values` is the reason this one is first: step 4.2 runs its bootstrap on
 * those replicates, and a missing or non-finite entry there is a decision made
 * on numbers nobody produced.
 */
const isBuildEvolveproInputResult: MameResultValidator = (value) =>
  isRecord(value) &&
  isString(value.output_path) &&
  isFiniteNumber(value.n_variants) &&
  isFiniteNumber(value.n_authoritative) &&
  isFiniteNumber(value.n_fallback_only) &&
  isStringArray(value.warnings) &&
  Array.isArray(value.mismatched) &&
  value.mismatched.every(isMismatchedVariant) &&
  isFiniteNumber(value.n_ngs_excluded) &&
  isStringArray(value.ngs_excluded) &&
  isString(value.gc_export_path) &&
  isLabelAudit(value.label_audit) &&
  isString(value.manifest_path) &&
  isString(value.primary_format) &&
  isFiniteNumber(value.input_count) &&
  isFiniteNumber(value.evaluable_count) &&
  isRecordOfFiniteNumber(value.exclusion_reason_counts) &&
  isStringArray(value.normalization_sources) &&
  isString(value.evidence_hash) &&
  isRecordOfString(value.artifact_hashes) &&
  isFiniteNumberArray(value.wt_values);

/**
 * `strategy.classify_round`.
 *
 * Two success shapes discriminated on `advisory`; anything else is refused, so
 * a payload carrying neither cannot reach the card as a blank decision.
 */
const isClassifyRoundResult: MameResultValidator = (value) => {
  if (!isRecord(value)) return false;
  if (value.advisory === "decision") {
    return (
      isString(value.label) &&
      isString(value.reason) &&
      isNullableFiniteNumber(value.confidence) &&
      isStringArray(value.missing_inputs)
    );
  }
  if (value.advisory === "not_assessable") {
    return (
      isString(value.reason) &&
      isStringArray(value.missing_inputs) &&
      isStringArray(value.blocked_decisions) &&
      (value.wt_replicate_count === undefined ||
        isFiniteNumber(value.wt_replicate_count)) &&
      (value.wt_replicate_min === undefined ||
        isFiniteNumber(value.wt_replicate_min))
    );
  }
  return false;
};

/** `mame.build_well_layout`. */
const isBuildWellLayoutResult: MameResultValidator = (value) =>
  isRecord(value) &&
  Array.isArray(value.draft) &&
  value.draft.every(
    (row) => isRecord(row) && isString(row.well) && isString(row.sample),
  ) &&
  isFiniteNumber(value.count) &&
  isStringArray(value.dropped_mutant_ids);

const VALIDATORS: Record<string, MameResultValidator> = {
  "mame.activity.build_evolvepro_input": isBuildEvolveproInputResult,
  "strategy.classify_round": isClassifyRoundResult,
  "mame.build_well_layout": isBuildWellLayoutResult,
};

/**
 * MAME dispatcher methods this table does NOT check yet, listed rather than
 * implied. Keep it in step with `python-core/sidecar_mame/dispatcher.py`
 * `_METHODS`.
 *
 * Three groups, and none of them is "safe by inspection":
 *
 *  - The large analyze contract (`analyze`, `load_analyze_result`,
 *    `get_plate_data`, `demux_and_filter`, `mame.run_combinatorial_demux`,
 *    `get_run_health`, `validate_inputs`, `check_plate_order`). These carry the
 *    most scientific numbers in the app and the widest result types (hundreds
 *    of fields across `src/types/mame/models.ts`), so guarding them is its own
 *    change with its own tests rather than a rushed shallow check that would
 *    read as coverage without being it.
 *  - Export and file-writing calls (`export_excel`, `export_janus_mapping`,
 *    `export_janus_mapping_dry_run`, `export_run_report`,
 *    `generate_mame_package`, `mame.export_barcode_worklist`,
 *    `activity.export_evolvepro_xlsx`), whose results are paths and counts the
 *    UI mostly echoes back.
 *  - Small control and inspection calls (`ping`, `health_info`,
 *    `cancel_analyze`, `reset_state`, `shutdown`, `read_kuma_meta`,
 *    `inspect_variant_source`, `mame.ingest.parse_reference`,
 *    `mame.detect_native_barcodes`, `activity.upload`,
 *    `activity.set_plate_meta`, `activity.merge`,
 *    `mame.activity.merge_for_evolvepro`).
 */
export const MAME_UNVALIDATED_METHODS: readonly string[] = [
  "ping",
  "health_info",
  "analyze",
  "validate_inputs",
  "load_analyze_result",
  "export_excel",
  "get_plate_data",
  "export_janus_mapping",
  "export_janus_mapping_dry_run",
  "read_kuma_meta",
  "export_run_report",
  "cancel_analyze",
  "reset_state",
  "demux_and_filter",
  "get_run_health",
  "activity.upload",
  "activity.set_plate_meta",
  "activity.merge",
  "activity.export_evolvepro_xlsx",
  "mame.activity.merge_for_evolvepro",
  "generate_mame_package",
  "check_plate_order",
  "inspect_variant_source",
  "mame.ingest.parse_reference",
  "mame.run_combinatorial_demux",
  "mame.detect_native_barcodes",
  "mame.export_barcode_worklist",
  "shutdown",
];

/**
 * Return the guard for *method*, or `null` when this table does not cover it.
 *
 * `null` is "not checked", never "checked and fine". The caller sends the result
 * through unvalidated, which is what every MAME method did before this table
 * existed, and `MAME_UNVALIDATED_METHODS` is where that set is written down.
 */
export function getMameRpcResultValidator(
  method: string,
): MameResultValidator | null {
  return VALIDATORS[method] ?? null;
}

/** Method names this table checks. Exported for the coverage test. */
export function validatedMameMethods(): string[] {
  return Object.keys(VALIDATORS);
}
