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
import { MEASUREMENT_SOURCES } from "./detect_measurement_source";

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

function isRecordOfStringArray(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(isStringArray);
}

function isRecordOfFiniteNumberArray(value: unknown): boolean {
  return isRecord(value) && Object.values(value).every(isFiniteNumberArray);
}

/**
 * Membership guards for the declared string unions.
 *
 * A union checked with `isString` is a decoration: the type says four values
 * and the guard admits every string, so a fifth reaches a component that
 * switches on it. The KURO validators enforce theirs inline
 * (`src/types/validators.ts:475`); these do the same, and each list mirrors the
 * Python that produces it.
 */

/** `kuma_core/mame/activity/detect_measurement_source.py` (`MEASUREMENT_SOURCES`). */
const MEASUREMENT_SOURCE_NAMES = new Set<string>(MEASUREMENT_SOURCES);

/** `kuma_core/strategy/classify.py:68` (`DecisionLabel`). */
const DECISION_LABELS = new Set([
  "continue_walking",
  "switch_combinatorial",
  "stop",
  "deferred",
]);

/**
 * `python-core/sidecar_mame/handlers/classify_round.py:137,140`
 * (`_REASON_WT_MISSING`, `_REASON_WT_INSUFFICIENT`), the only two values the
 * `not_assessable` shape reports.
 */
const NOT_ASSESSABLE_REASONS = new Set([
  "wt_replicates_missing",
  "wt_replicates_insufficient",
]);

/**
 * `kuma_core/mame/activity/build_evolvepro_input.py:364`, where exactly one of
 * the three primary sources must be supplied and its name becomes this field.
 */
const PRIMARY_FORMATS = new Set([
  "activity_path",
  "gc_data_xlsx",
  "round1_report_xlsx",
]);

/**
 * `kuma_core/mame/activity/label_audit.py:173,190-196,232`, every `category=`
 * a `LabelFinding` is constructed with.
 */
const LABEL_FINDING_CATEGORIES = new Set([
  "not_introduced",
  "wrong_residue",
  "extra_mutation",
  "sequence_collapse",
  "cross_well",
]);

/**
 * `kuma_core/mame/activity/label_audit.py:92-97`, the four returns of
 * `_classify_geometry`. `null` when no closed permutation was found.
 */
const LABEL_AUDIT_GEOMETRIES = new Set([
  "two_swap",
  "contiguous_shift",
  "scattered",
  "global_offset",
]);

function isMemberOf(members: Set<string>): (value: unknown) => boolean {
  return (value) => isString(value) && members.has(value);
}

const isDecisionLabel = isMemberOf(DECISION_LABELS);

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
    isMemberOf(LABEL_FINDING_CATEGORIES)(value.category) &&
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
    (value.geometry === null || isMemberOf(LABEL_AUDIT_GEOMETRIES)(value.geometry))
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
  isMemberOf(PRIMARY_FORMATS)(value.primary_format) &&
  isFiniteNumber(value.input_count) &&
  isFiniteNumber(value.evaluable_count) &&
  isRecordOfFiniteNumber(value.exclusion_reason_counts) &&
  isStringArray(value.normalization_sources) &&
  isString(value.evidence_hash) &&
  isRecordOfString(value.artifact_hashes) &&
  isFiniteNumberArray(value.wt_values) &&
  isRecordOfFiniteNumberArray(value.variant_replicates);

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
      // `label` gates a badge and a colour in AdvisoryDecisionCard, which
      // renders it through `t("advisoryDecision.labels.<label>")` with no
      // membership check of its own. An unlisted label reaches the badge as an
      // i18n key miss, so it is refused here instead.
      isDecisionLabel(value.label) &&
      // `reason` is deliberately NOT enumerated: `Decision.reason` is a bare
      // `str` in kuma_core/strategy/classify.py:75, and the card already falls
      // back to `humanize` for a code with no phrase.
      isString(value.reason) &&
      isNullableFiniteNumber(value.confidence) &&
      isStringArray(value.missing_inputs)
    );
  }
  if (value.advisory === "not_assessable") {
    return (
      // Only the two shortfalls the handler distinguishes. Unlike the decision
      // branch this `reason` IS a closed set: classify_round.py:137,140 are the
      // only values assigned at classify_round.py:607.
      isMemberOf(NOT_ASSESSABLE_REASONS)(value.reason) &&
      isStringArray(value.missing_inputs) &&
      // Rendered through the same `advisoryDecision.labels.*` keys as `label`.
      Array.isArray(value.blocked_decisions) &&
      value.blocked_decisions.every(isDecisionLabel) &&
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

/**
 * `health_info`.
 *
 * `python-core/sidecar_mame/dispatcher.py:59-72` returns
 * `{"pid": os.getpid(), "rss_bytes": <int>, "py_version": <str>}`, character for
 * character the same dict the KURO dispatcher builds at
 * `python-core/sidecar_kuro/dispatcher.py:69-82`, so the two channels guard it
 * with the same three checks. `rss_bytes` degrades to `0` rather than
 * disappearing when the memory-monitor import fails, so no field is optional.
 */
const isHealthInfoResult: MameResultValidator = (value) =>
  isRecord(value) &&
  isFiniteNumber(value.pid) &&
  isFiniteNumber(value.rss_bytes) &&
  isString(value.py_version);

/**
 * `inspect_variant_source`.
 *
 * `python-core/sidecar_mame/handlers/barcode_package.py:90` has one return path.
 * Two fields need care and neither is guessable from the TypeScript type:
 *
 *  - `sheets` is an EMPTY list for CSV/TSV/TXT input, not absent
 *    (`kuma_core/mame/ingest/variant_list.py:164`), so `[]` is a valid answer
 *    and not a signal of failure.
 *  - `suggested_column` is genuinely nullable: it is always `None` when
 *    `is_kuro_export` is true (`variant_list.py:189-191`), and `None` again for
 *    a non-KURO file whose headers match no known column.
 *
 * `headers` is `dict[str, list[str]]`, keyed by sheet name, or by the single
 * empty-string key `""` for CSV input (`variant_list.py:165`).
 */
const isInspectVariantSourceResult: MameResultValidator = (value) =>
  isRecord(value) &&
  typeof value.is_kuro_export === "boolean" &&
  isStringArray(value.sheets) &&
  isRecordOfStringArray(value.headers) &&
  (value.suggested_column === null || isString(value.suggested_column));

/**
 * `generate_mame_package`.
 *
 * `python-core/sidecar_mame/handlers/barcode_package.py:280`, serializing the
 * `MamePackageResult` dataclass at
 * `kuma_core/mame/ingest/barcode_package.py:594`. `amplicon_length` is nullable
 * by dataclass default (`barcode_package.py:600`); the three path fields are
 * stringified `Path` objects and are never null.
 */
const isMamePackageResult: MameResultValidator = (value) =>
  isRecord(value) &&
  isString(value.barcodes_xlsx) &&
  isString(value.amplicon_fa) &&
  isString(value.context_json) &&
  isStringArray(value.warnings) &&
  (value.amplicon_length === null || isFiniteNumber(value.amplicon_length));

/**
 * `read_kuma_meta`.
 *
 * The handler is typed `-> dict | None` and really does return `None`
 * (`python-core/sidecar_mame/handlers/kuma_meta.py:15-16`), for two reasons in
 * `kuma_core/mame/io/kuma_meta.py`: no `__kuma_meta__` sheet (`:28`), or the
 * sheet present but carrying no `project_id` (`:35`). So `null` is a SUCCESS
 * result here, not a shape failure, and the guard accepts it up front.
 *
 * When non-null it is `asdict` of the `KumaMeta` dataclass: exactly four string
 * fields, with missing values written as `""` rather than left null.
 */
const isReadKumaMetaResult: MameResultValidator = (value) => {
  if (value === null) return true;
  return (
    isRecord(value) &&
    isString(value.project_id) &&
    isString(value.kuma_version) &&
    isString(value.kuro_module_version) &&
    isString(value.exported_at)
  );
};

/**
 * `mame.activity.detect_measurement_source`.
 *
 * `python-core/sidecar_mame/handlers/activity.py` serialising
 * `DetectMeasurementSourceResult`. Two fields need care:
 *
 *  - `candidates` is a list, and an EMPTY list is a SUCCESS result: the file is
 *    none of the four step 4.1 sources, and `reason` says what was seen. Each
 *    member is checked for membership rather than for being a string, because
 *    the UI switches on it and a sixth value would reach that switch.
 *  - `evidence` is deliberately open (`dict[str, Any]` in Python), so it is
 *    checked for being a record and nothing more. Its keys differ by branch: a
 *    block workbook carries namespace counts, a header file carries the header.
 */
const isDetectMeasurementSourceResult: MameResultValidator = (value) =>
  isRecord(value) &&
  isString(value.path) &&
  Array.isArray(value.candidates) &&
  value.candidates.every(
    (candidate) => isString(candidate) && MEASUREMENT_SOURCE_NAMES.has(candidate),
  ) &&
  typeof value.ambiguous === "boolean" &&
  value.ambiguous === value.candidates.length > 1 &&
  isRecord(value.evidence) &&
  isString(value.reason);

const VALIDATORS: Record<string, MameResultValidator> = {
  "mame.activity.build_evolvepro_input": isBuildEvolveproInputResult,
  "mame.activity.detect_measurement_source": isDetectMeasurementSourceResult,
  "strategy.classify_round": isClassifyRoundResult,
  "mame.build_well_layout": isBuildWellLayoutResult,
  health_info: isHealthInfoResult,
  inspect_variant_source: isInspectVariantSourceResult,
  generate_mame_package: isMamePackageResult,
  read_kuma_meta: isReadKumaMetaResult,
};

/**
 * MAME dispatcher methods this table does NOT check yet, listed rather than
 * implied. Keep it in step with `python-core/sidecar_mame/dispatcher.py`
 * `_METHODS`.
 *
 * Three groups, and none of them is "safe by inspection":
 *
 *  - The large analyze contract (`analyze`, `load_analyze_result`,
 *    `get_plate_data`, `mame.run_combinatorial_demux`,
 *    `get_run_health`, `validate_inputs`, `check_plate_order`). These carry the
 *    most scientific numbers in the app and the widest result types (hundreds
 *    of fields across `src/types/mame/models.ts`), so guarding them is its own
 *    change with its own tests rather than a rushed shallow check that would
 *    read as coverage without being it.
 *  - Export and file-writing calls (`export_excel`, `export_janus_mapping`,
 *    `export_janus_mapping_dry_run`, `export_run_report`,
 *    `generate_mame_package`, `mame.export_barcode_worklist`,
 *    `activity.export_evolvepro_xlsx`, `export_variant_template`), whose
 *    results are paths and counts the UI mostly echoes back.
 *  - Small control and inspection calls (`ping`, `health_info`,
 *    `reset_state`, `shutdown`, `read_kuma_meta`,
 *    `inspect_variant_source`, `mame.ingest.parse_reference`,
 *    `mame.detect_native_barcodes`, `activity.upload`,
 *    `activity.set_plate_meta`, `activity.merge`,
 *    `mame.activity.merge_for_evolvepro`).
 */
export const MAME_UNVALIDATED_METHODS: readonly string[] = [
  "ping",
  "analyze",
  "validate_inputs",
  "load_analyze_result",
  "export_excel",
  "get_plate_data",
  "export_janus_mapping",
  "export_janus_mapping_dry_run",
  "export_run_report",
  "reset_state",
  "get_run_health",
  "activity.upload",
  "activity.set_plate_meta",
  "activity.merge",
  "activity.export_evolvepro_xlsx",
  "mame.activity.merge_for_evolvepro",
  "check_plate_order",
  "mame.ingest.parse_reference",
  "mame.run_combinatorial_demux",
  "mame.detect_native_barcodes",
  "mame.export_barcode_worklist",
  "export_variant_template",
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
