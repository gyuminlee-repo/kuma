/** Project-scoped persisted state for the Step 3 EVOLVEpro input builder. */
import { isResequenceEvidence, type ResequenceEvidence } from "@/types/mame/resequence";
import type { ExcludedGcRow, GcSourceField } from "@/types/mame/build_evolvepro_input";

export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro";
const STORAGE_VERSION = 2;

export type BuildEvolveproPrimarySource = "longFormat" | "gcSheet" | "rawReport" | "numericReport";
export type BuildEvolveproConfirmationSource = "none" | "variantLabels" | "numericIds" | "wellLabels";
// Forms saved before "wellLabels" existed hold one of the first three and still load.
const CONFIRMATION_SOURCES = ["none", "variantLabels", "numericIds", "wellLabels"];

export interface BuildEvolveproFormState {
  primarySource: BuildEvolveproPrimarySource;
  confirmationSource: BuildEvolveproConfirmationSource;
  activityPath: string;
  activityScale: "raw" | "relative_to_wt";
  mismatchThreshold: number;
  layoutXlsx: string;
  gcDataXlsx: string;
  round1ReportXlsx: string;
  numericReportXlsx: string;
  remeasureReportXlsx: string;
  remeasureNumericXlsx: string;
  remeasureWellXlsx: string;
  /**
   * Designed variant list, the order source a numeric-ID report is decoded
   * against. Preferred over the hand-written plate file: it states the order
   * the run was placed in.
   */
  expectedXlsx: string;
  verdictXlsx: string;
  resequenceEvidence?: ResequenceEvidence | null;
  verdictEvidenceSignature: string;
  outputXlsx: string;
  /**
   * The round id `outputXlsx` was generated for, or "" when the operator
   * browsed to it. Non-empty means this panel wrote the path and may rewrite it
   * for the next round; empty means hands off.
   */
  outputXlsxRoundId: string;
  /**
   * GC rows the operator unticked in the row review, each as it read then.
   * Sent as `excluded_rows`. Emptied whenever an input the review was read
   * from changes (see `applyBuildEvolveproPatch`).
   */
  excludedRows: ExcludedGcRow[];
  migrationNotice: boolean;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  primarySource: "longFormat",
  confirmationSource: "none",
  activityPath: "",
  activityScale: "raw",
  mismatchThreshold: 0.1,
  layoutXlsx: "",
  gcDataXlsx: "",
  round1ReportXlsx: "",
  numericReportXlsx: "",
  remeasureReportXlsx: "",
  remeasureNumericXlsx: "",
  remeasureWellXlsx: "",
  expectedXlsx: "",
  verdictXlsx: "",
  resequenceEvidence: null,
  verdictEvidenceSignature: "",
  outputXlsx: "",
  outputXlsxRoundId: "",
  excludedRows: [],
  migrationNotice: false,
};

function storageKey(projectPath: string): string {
  return `${BUILD_EVOLVEPRO_STORAGE_KEY}:v${STORAGE_VERSION}:${encodeURIComponent(projectPath)}`;
}

function stringValue(payload: Record<string, unknown>, key: string): string {
  return typeof payload[key] === "string" ? payload[key] : "";
}

const GC_SOURCE_FIELDS: readonly GcSourceField[] = [
  "activity_path",
  "gc_data_xlsx",
  "round1_report_xlsx",
  "numeric_report_xlsx",
  "remeasure_report_xlsx",
  "remeasure_numeric_xlsx",
  "remeasure_well_xlsx",
];

function isNullableFinite(value: unknown): value is number | null | undefined {
  return value === null || value === undefined || (typeof value === "number" && Number.isFinite(value));
}

/** Rows saved by this build of the panel; anything else (older saves, edits) is dropped. */
function readExcludedRows(value: unknown): ExcludedGcRow[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) return [];
    const row = item as Record<string, unknown>;
    if (
      typeof row.source !== "string" ||
      !GC_SOURCE_FIELDS.includes(row.source as GcSourceField) ||
      typeof row.row_index !== "number" ||
      !Number.isInteger(row.row_index) ||
      typeof row.sample_name !== "string" ||
      !isNullableFinite(row.block_index) ||
      !isNullableFinite(row.area)
    ) {
      return [];
    }
    return [{
      source: row.source as GcSourceField,
      row_index: row.row_index,
      block_index: row.block_index ?? null,
      sample_name: row.sample_name,
      area: row.area ?? null,
    }];
  });
}

/**
 * The inputs a row review was read from. A review describes these files read
 * against this mapping and evidence; once any of them changes, the rows the
 * operator unticked may name other rows or none.
 */
export function buildEvolveproReviewSignature(state: BuildEvolveproFormState): string {
  return JSON.stringify([
    state.primarySource,
    state.confirmationSource,
    state.activityPath,
    state.activityScale,
    state.gcDataXlsx,
    state.round1ReportXlsx,
    state.numericReportXlsx,
    state.remeasureReportXlsx,
    state.remeasureNumericXlsx,
    state.remeasureWellXlsx,
    state.layoutXlsx,
    state.verdictXlsx,
    state.expectedXlsx,
    state.resequenceEvidence ?? null,
  ]);
}

/**
 * Apply a form edit. When the edit changes an input the row review was read
 * from, the operator's unticked rows are emptied; picking the same value again
 * keeps them. An edit that sets `excludedRows` itself is taken as given.
 */
export function applyBuildEvolveproPatch(
  previous: BuildEvolveproFormState,
  partial: Partial<BuildEvolveproFormState>,
): BuildEvolveproFormState {
  const next = { ...previous, ...partial, migrationNotice: false };
  if (
    !("excludedRows" in partial) &&
    buildEvolveproReviewSignature(next) !== buildEvolveproReviewSignature(previous)
  ) {
    next.excludedRows = [];
  }
  return next;
}

function pathBelongsToProject(path: string, projectPath: string): boolean {
  const normalizedPath = path.replace(/\\/g, "/").replace(/\/+$/, "");
  const normalizedProject = projectPath.replace(/\\/g, "/").replace(/\/+$/, "");
  if (/^(?:[a-z]:\/|\/\/)/i.test(normalizedProject)) {
    return normalizedPath.toLowerCase().startsWith(`${normalizedProject.toLowerCase()}/`);
  }
  return normalizedPath.startsWith(`${normalizedProject}/`);
}

const PROJECT_PATH_PREFIX = "@project/";
const CURRENT_PATH_KEYS = [
  "activityPath",
  "layoutXlsx",
  "gcDataXlsx",
  "round1ReportXlsx",
  "numericReportXlsx",
  "remeasureReportXlsx",
  "remeasureNumericXlsx",
  "remeasureWellXlsx",
  "expectedXlsx",
  "verdictXlsx",
  "outputXlsx",
] as const;

function toPortablePath(path: string, projectPath: string): string {
  if (!path || !pathBelongsToProject(path, projectPath)) return path;
  const normalizedPath = path.replace(/\\/g, "/");
  const normalizedProject = projectPath.replace(/\\/g, "/").replace(/\/+$/, "");
  return `${PROJECT_PATH_PREFIX}${normalizedPath.slice(normalizedProject.length + 1)}`;
}

function fromPortablePath(path: string, projectPath: string): string {
  if (!path.startsWith(PROJECT_PATH_PREFIX)) return path;
  const relative = path.slice(PROJECT_PATH_PREFIX.length);
  const separator = projectPath.includes("\\") ? "\\" : "/";
  return `${projectPath.replace(/[\\/]+$/, "")}${separator}${relative.replace(/\//g, separator)}`;
}
const LEGACY_PATH_KEYS = [
  "activityPath",
  "layoutXlsx",
  "gcDataXlsx",
  "round1ReportXlsx",
  "numericReportXlsx",
  "remeasureReportXlsx",
  "remeasureNumericXlsx",
  "remeasureWellXlsx",
  "expectedXlsx",
  "verdictXlsx",
  "outputXlsx",
  "round1EvolveproXlsx",
  "round1RepBatchXlsx",
  "expectedMutationsXlsx",
  "remeasureRepBatchXlsx",
  "repBatchXlsx",
  "prevEvolveproXlsx",
] as const;


// A legacy record with no paths at all carries no evidence either way: it is
// not "another project's data" the way a record whose paths point elsewhere
// is, it is a record that never states a project. `paths.every(...)` on an
// empty array is vacuously true, which is the right reading here: there is
// nothing to contradict adoption, so importing it costs nothing (there are no
// foreign paths to inherit) and unblocks whatever primarySource/verdictXlsx/
// etc. fields it does carry. Before this, an empty-paths record read as
// belonging to no project, forcing `migrationNotice: true`, which makes
// `seedBuildEvolveproForm` a permanent no-op (it bails on
// `current.migrationNotice`) and leaves the panel stuck on "Unsupported saved
// mode" with no way to clear it short of wiping localStorage by hand.
function legacyPathsBelongToProject(payload: Record<string, unknown>, projectPath: string): boolean {
  const paths = LEGACY_PATH_KEYS
    .map((key) => stringValue(payload, key))
    .filter(Boolean);
  return paths.every((path) => pathBelongsToProject(path, projectPath));
}

function hasRemovedSelection(payload: Record<string, unknown>): boolean {
  const primarySource = typeof payload.primarySource === "string" ? payload.primarySource : "";
  const confirmationSource =
    typeof payload.confirmationSource === "string" ? payload.confirmationSource : "";
  return (Boolean(primarySource) &&
      !["longFormat", "gcSheet", "rawReport", "numericReport"].includes(primarySource)) ||
    (Boolean(confirmationSource) &&
      !CONFIRMATION_SOURCES.includes(confirmationSource)) ||
    payload.sourceMode === "rank" ||
    (payload.sourceMode === "reports" && payload.round1Source !== "raw") ||
    ["prev", "numeric"].includes(String(payload.round1Source));
}

function readState(
  payload: Record<string, unknown>,
  projectPath: string,
): BuildEvolveproFormState {
  const primarySource = ["longFormat", "gcSheet", "rawReport", "numericReport"].includes(String(payload.primarySource))
    ? payload.primarySource as BuildEvolveproPrimarySource
    : payload.sourceMode === "reports" && payload.round1Source === "raw"
      ? "rawReport"
      : BUILD_EVOLVEPRO_DEFAULT_STATE.primarySource;
  const confirmationSource = CONFIRMATION_SOURCES.includes(String(payload.confirmationSource))
    ? payload.confirmationSource as BuildEvolveproConfirmationSource
    : payload.sourceMode === "reports" && stringValue(payload, "remeasureReportXlsx")
      ? "variantLabels"
      : BUILD_EVOLVEPRO_DEFAULT_STATE.confirmationSource;
  return {
    primarySource,
    confirmationSource,
    activityPath: fromPortablePath(stringValue(payload, "activityPath"), projectPath),
    activityScale: payload.activityScale === "relative_to_wt" ? "relative_to_wt" : "raw",
    mismatchThreshold:
      typeof payload.mismatchThreshold === "number" &&
      Number.isFinite(payload.mismatchThreshold) &&
      payload.mismatchThreshold > 0
        ? payload.mismatchThreshold
        : BUILD_EVOLVEPRO_DEFAULT_STATE.mismatchThreshold,
    layoutXlsx: fromPortablePath(stringValue(payload, "layoutXlsx"), projectPath),
    gcDataXlsx: fromPortablePath(stringValue(payload, "gcDataXlsx"), projectPath),
    round1ReportXlsx: fromPortablePath(stringValue(payload, "round1ReportXlsx"), projectPath),
    numericReportXlsx: fromPortablePath(stringValue(payload, "numericReportXlsx"), projectPath),
    remeasureReportXlsx: fromPortablePath(stringValue(payload, "remeasureReportXlsx"), projectPath),
    remeasureNumericXlsx: fromPortablePath(stringValue(payload, "remeasureNumericXlsx"), projectPath),
    // Absent on records saved before well-labeled confirmation existed.
    remeasureWellXlsx: fromPortablePath(stringValue(payload, "remeasureWellXlsx"), projectPath),
    expectedXlsx: fromPortablePath(stringValue(payload, "expectedXlsx"), projectPath),
    verdictXlsx: fromPortablePath(stringValue(payload, "verdictXlsx"), projectPath),
    resequenceEvidence: isResequenceEvidence(payload.resequenceEvidence) ? {
      ...payload.resequenceEvidence,
      original_verdict_xlsx: fromPortablePath(payload.resequenceEvidence.original_verdict_xlsx, projectPath),
      verdict_xlsx: fromPortablePath(payload.resequenceEvidence.verdict_xlsx, projectPath),
    } : null,
    verdictEvidenceSignature: stringValue(payload, "verdictEvidenceSignature"),
    outputXlsx: fromPortablePath(stringValue(payload, "outputXlsx"), projectPath),
    // Absent on records saved before per-round output paths existed, and empty
    // is the safe reading of those: treat the stored path as hand-picked and
    // leave it alone rather than rewriting a destination this build never set.
    outputXlsxRoundId: stringValue(payload, "outputXlsxRoundId"),
    // Absent on records saved before the row review existed: nothing unticked.
    excludedRows: readExcludedRows(payload.excludedRows),
    migrationNotice: Boolean(payload.migrationNotice),
  };
}

/** Loads only the active project's state. A legacy global record is imported only when every stored path belongs to it. */
export function loadBuildEvolveproFromStorage(projectPath?: string | null): BuildEvolveproFormState {
  if (!projectPath) return BUILD_EVOLVEPRO_DEFAULT_STATE;
  try {
    const scopedRaw = localStorage.getItem(storageKey(projectPath));
    if (scopedRaw) {
      const scoped = JSON.parse(scopedRaw) as Record<string, unknown>;
      if (hasRemovedSelection(scoped)) {
        return { ...BUILD_EVOLVEPRO_DEFAULT_STATE, migrationNotice: true };
      }
      return readState(scoped, projectPath);
    }
    const legacyRaw = localStorage.getItem(BUILD_EVOLVEPRO_STORAGE_KEY);
    if (!legacyRaw) return BUILD_EVOLVEPRO_DEFAULT_STATE;
    const legacy = JSON.parse(legacyRaw) as Record<string, unknown>;
    if (hasRemovedSelection(legacy) || !legacyPathsBelongToProject(legacy, projectPath)) {
      return { ...BUILD_EVOLVEPRO_DEFAULT_STATE, migrationNotice: true };
    }
    const imported = readState(legacy, projectPath);
    saveBuildEvolveproToStorage(imported, projectPath);
    if (localStorage.getItem(storageKey(projectPath))) {
      localStorage.removeItem(BUILD_EVOLVEPRO_STORAGE_KEY);
    }
    return imported;
  } catch {
    return BUILD_EVOLVEPRO_DEFAULT_STATE;
  }
}

export function saveBuildEvolveproToStorage(state: BuildEvolveproFormState, projectPath?: string | null): void {
  if (!projectPath) return;
  try {
    const portable = { ...state } as Record<string, unknown>;
    if (state.resequenceEvidence) {
      portable.resequenceEvidence = {
        ...state.resequenceEvidence,
        original_verdict_xlsx: toPortablePath(state.resequenceEvidence.original_verdict_xlsx, projectPath),
        verdict_xlsx: toPortablePath(state.resequenceEvidence.verdict_xlsx, projectPath),
      };
    }
    for (const key of CURRENT_PATH_KEYS) {
      portable[key] = toPortablePath(state[key], projectPath);
    }
    localStorage.setItem(
      storageKey(projectPath),
      JSON.stringify({ version: STORAGE_VERSION, projectPath, ...portable }),
    );
  } catch {
    // Ignore persistence failures; the current form remains usable.
  }
}

/**
 * A numeric sample name states a position, so decoding one needs the order the
 * plate was filled in. Exactly one source answers it, and the design list is
 * the one to reach for.
 */
export function hasBuildEvolveproOrderSource(state: BuildEvolveproFormState): boolean {
  return Boolean(state.expectedXlsx) !== Boolean(state.layoutXlsx);
}

export function buildEvolveproNeedsOrderSource(state: BuildEvolveproFormState): boolean {
  return state.primarySource === "numericReport" || state.confirmationSource === "numericIds";
}

export function hasBuildEvolveproPrimaryInputs(state: BuildEvolveproFormState): boolean {
  switch (state.primarySource) {
    case "longFormat": return Boolean(state.activityPath);
    case "gcSheet": return Boolean(state.gcDataXlsx);
    case "rawReport": return Boolean(state.round1ReportXlsx);
    case "numericReport": return Boolean(state.numericReportXlsx);
  }
}

export function hasBuildEvolveproConfirmationInputs(state: BuildEvolveproFormState): boolean {
  switch (state.confirmationSource) {
    case "none": return true;
    case "variantLabels": return Boolean(state.remeasureReportXlsx);
    case "numericIds": return Boolean(state.remeasureNumericXlsx);
    case "wellLabels": return Boolean(state.remeasureWellXlsx);
  }
}

export function isBuildEvolveproFormReady(state: BuildEvolveproFormState): boolean {
  return !state.migrationNotice && Boolean(state.verdictXlsx && state.outputXlsx) &&
    hasBuildEvolveproPrimaryInputs(state) && hasBuildEvolveproConfirmationInputs(state) &&
    (!buildEvolveproNeedsOrderSource(state) || hasBuildEvolveproOrderSource(state));
}

export interface BuildEvolveproCompletionRecord { outputPath: string; signature: string; }

/**
 * Identity of the request this form describes.
 *
 * `outputXlsxRoundId` is excluded alongside `migrationNotice`: it records which
 * round the panel derived `outputXlsx` for, and is not sent to the sidecar. It
 * says nothing the signature does not already carry, since a round change that
 * moves the destination rewrites `outputXlsx` itself (BuildEvolveproInputPanel)
 * and that field is in the signature. Excluding it keeps the signature a
 * description of the request rather than of how the path was arrived at.
 */
export function buildEvolveproFormSignature(state: BuildEvolveproFormState): string {
  const {
    migrationNotice: _migrationNotice,
    outputXlsxRoundId: _outputXlsxRoundId,
    ...requestState
  } = state;
  return JSON.stringify(requestState);
}

export function createBuildEvolveproCompletion(state: BuildEvolveproFormState, outputPath: string): BuildEvolveproCompletionRecord {
  return { outputPath, signature: buildEvolveproFormSignature(state) };
}

export function hasCompletedBuildEvolveproOutput(state: BuildEvolveproFormState, completion: BuildEvolveproCompletionRecord | null): boolean {
  return isBuildEvolveproFormReady(state) && completion?.outputPath === state.outputXlsx &&
    completion.signature === buildEvolveproFormSignature(state);
}

export function hasBuildEvolveproFormValues(state: BuildEvolveproFormState): boolean {
  return state.migrationNotice || Object.entries(state).some(([key, value]) =>
    key !== "migrationNotice" &&
    (key === "excludedRows"
      ? state.excludedRows.length > 0
      : value !== BUILD_EVOLVEPRO_DEFAULT_STATE[key as keyof BuildEvolveproFormState]));
}

/** Seeds supported sample inputs into one project's form without overwriting user choices. */
export function seedBuildEvolveproForm(
  paths: Partial<Pick<
    BuildEvolveproFormState,
    | "activityPath"
    | "layoutXlsx"
    | "gcDataXlsx"
    | "round1ReportXlsx"
    | "numericReportXlsx"
    | "remeasureReportXlsx"
    | "remeasureNumericXlsx"
    | "remeasureWellXlsx"
    | "expectedXlsx"
    | "verdictXlsx"
    | "outputXlsx"
  >>,
  projectPath?: string | null,
): void {
  if (!projectPath) return;
  const current = loadBuildEvolveproFromStorage(projectPath);
  if (current.migrationNotice) return;

  const next = { ...current };
  for (const [key, value] of Object.entries(paths) as Array<
    [keyof typeof paths, string | undefined]
  >) {
    if (value && !next[key]) {
      next[key] = value as never;
    }
  }

  if (current.primarySource === "longFormat" && !current.activityPath) {
    if (paths.activityPath) next.primarySource = "longFormat";
    else if (paths.gcDataXlsx) next.primarySource = "gcSheet";
    else if (paths.round1ReportXlsx) next.primarySource = "rawReport";
    else if (paths.numericReportXlsx) next.primarySource = "numericReport";
  }
  if (current.confirmationSource === "none" && !current.remeasureReportXlsx) {
    if (paths.remeasureReportXlsx) next.confirmationSource = "variantLabels";
    else if (paths.remeasureNumericXlsx) next.confirmationSource = "numericIds";
    else if (paths.remeasureWellXlsx) next.confirmationSource = "wellLabels";
  }
  // The same rule as an operator's own edit (applyBuildEvolveproPatch): a
  // seeded file the review reads makes the saved unticks name another file.
  if (buildEvolveproReviewSignature(next) !== buildEvolveproReviewSignature(current)) {
    next.excludedRows = [];
  }
  saveBuildEvolveproToStorage(next, projectPath);
}
