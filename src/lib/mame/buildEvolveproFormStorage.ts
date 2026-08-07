/** Project-scoped persisted state for the Step 3 EVOLVEpro input builder. */

export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro";
const STORAGE_VERSION = 2;

export type BuildEvolveproPrimarySource = "longFormat" | "gcSheet" | "rawReport";
export type BuildEvolveproConfirmationSource = "none" | "variantLabels";

export interface BuildEvolveproFormState {
  primarySource: BuildEvolveproPrimarySource;
  confirmationSource: BuildEvolveproConfirmationSource;
  activityPath: string;
  activityScale: "raw" | "relative_to_wt";
  layoutXlsx: string;
  gcDataXlsx: string;
  round1ReportXlsx: string;
  remeasureReportXlsx: string;
  verdictXlsx: string;
  verdictEvidenceSignature: string;
  outputXlsx: string;
  /**
   * The round id `outputXlsx` was generated for, or "" when the operator
   * browsed to it. Non-empty means this panel wrote the path and may rewrite it
   * for the next round; empty means hands off.
   */
  outputXlsxRoundId: string;
  migrationNotice: boolean;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  primarySource: "longFormat",
  confirmationSource: "none",
  activityPath: "",
  activityScale: "raw",
  layoutXlsx: "",
  gcDataXlsx: "",
  round1ReportXlsx: "",
  remeasureReportXlsx: "",
  verdictXlsx: "",
  verdictEvidenceSignature: "",
  outputXlsx: "",
  outputXlsxRoundId: "",
  migrationNotice: false,
};

function storageKey(projectPath: string): string {
  return `${BUILD_EVOLVEPRO_STORAGE_KEY}:v${STORAGE_VERSION}:${encodeURIComponent(projectPath)}`;
}

function stringValue(payload: Record<string, unknown>, key: string): string {
  return typeof payload[key] === "string" ? payload[key] : "";
}

function pathBelongsToProject(path: string, projectPath: string): boolean {
  const normalizedPath = path.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  const normalizedProject = projectPath.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return normalizedPath.startsWith(`${normalizedProject}/`);
}

const PROJECT_PATH_PREFIX = "@project/";
const CURRENT_PATH_KEYS = [
  "activityPath",
  "layoutXlsx",
  "gcDataXlsx",
  "round1ReportXlsx",
  "remeasureReportXlsx",
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
  "remeasureReportXlsx",
  "verdictXlsx",
  "outputXlsx",
  "round1EvolveproXlsx",
  "round1RepBatchXlsx",
  "expectedMutationsXlsx",
  "remeasureRepBatchXlsx",
  "repBatchXlsx",
  "prevEvolveproXlsx",
] as const;


function legacyPathsBelongToProject(payload: Record<string, unknown>, projectPath: string): boolean {
  const paths = LEGACY_PATH_KEYS
    .map((key) => stringValue(payload, key))
    .filter(Boolean);
  return paths.length > 0 && paths.every((path) => pathBelongsToProject(path, projectPath));
}

function hasRemovedSelection(payload: Record<string, unknown>): boolean {
  const primarySource = typeof payload.primarySource === "string" ? payload.primarySource : "";
  const confirmationSource =
    typeof payload.confirmationSource === "string" ? payload.confirmationSource : "";
  return (Boolean(primarySource) &&
      !["longFormat", "gcSheet", "rawReport"].includes(primarySource)) ||
    (Boolean(confirmationSource) &&
      !["none", "variantLabels"].includes(confirmationSource)) ||
    payload.sourceMode === "rank" ||
    (payload.sourceMode === "reports" && payload.round1Source !== "raw") ||
    ["prev", "numeric"].includes(String(payload.round1Source));
}

function readState(
  payload: Record<string, unknown>,
  projectPath: string,
): BuildEvolveproFormState {
  const primarySource = ["longFormat", "gcSheet", "rawReport"].includes(String(payload.primarySource))
    ? payload.primarySource as BuildEvolveproPrimarySource
    : payload.sourceMode === "reports" && payload.round1Source === "raw"
      ? "rawReport"
      : BUILD_EVOLVEPRO_DEFAULT_STATE.primarySource;
  const confirmationSource = ["none", "variantLabels"].includes(String(payload.confirmationSource))
    ? payload.confirmationSource as BuildEvolveproConfirmationSource
    : payload.sourceMode === "reports" && stringValue(payload, "remeasureReportXlsx")
      ? "variantLabels"
      : BUILD_EVOLVEPRO_DEFAULT_STATE.confirmationSource;
  return {
    primarySource,
    confirmationSource,
    activityPath: fromPortablePath(stringValue(payload, "activityPath"), projectPath),
    activityScale: payload.activityScale === "relative_to_wt" ? "relative_to_wt" : "raw",
    layoutXlsx: fromPortablePath(stringValue(payload, "layoutXlsx"), projectPath),
    gcDataXlsx: fromPortablePath(stringValue(payload, "gcDataXlsx"), projectPath),
    round1ReportXlsx: fromPortablePath(stringValue(payload, "round1ReportXlsx"), projectPath),
    remeasureReportXlsx: fromPortablePath(stringValue(payload, "remeasureReportXlsx"), projectPath),
    verdictXlsx: fromPortablePath(stringValue(payload, "verdictXlsx"), projectPath),
    verdictEvidenceSignature: stringValue(payload, "verdictEvidenceSignature"),
    outputXlsx: fromPortablePath(stringValue(payload, "outputXlsx"), projectPath),
    // Absent on records saved before per-round output paths existed, and empty
    // is the safe reading of those: treat the stored path as hand-picked and
    // leave it alone rather than rewriting a destination this build never set.
    outputXlsxRoundId: stringValue(payload, "outputXlsxRoundId"),
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

export function hasBuildEvolveproPrimaryInputs(state: BuildEvolveproFormState): boolean {
  switch (state.primarySource) {
    case "longFormat": return Boolean(state.activityPath);
    case "gcSheet": return Boolean(state.gcDataXlsx && state.layoutXlsx);
    case "rawReport": return Boolean(state.round1ReportXlsx && state.layoutXlsx);
  }
}

export function hasBuildEvolveproConfirmationInputs(state: BuildEvolveproFormState): boolean {
  return state.confirmationSource === "none" || Boolean(state.remeasureReportXlsx);
}

export function isBuildEvolveproFormReady(state: BuildEvolveproFormState): boolean {
  return !state.migrationNotice && Boolean(state.verdictXlsx && state.outputXlsx) &&
    hasBuildEvolveproPrimaryInputs(state) && hasBuildEvolveproConfirmationInputs(state);
}

export interface BuildEvolveproCompletionRecord { outputPath: string; signature: string; }

/**
 * Identity of the request this form describes.
 *
 * `outputXlsxRoundId` is excluded alongside `migrationNotice`: it records which
 * round the panel derived the path for, and is not sent to the sidecar. Letting
 * it into the signature would mark a finished build stale the moment the active
 * round changed, without any input having moved.
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
    key !== "migrationNotice" && value !== BUILD_EVOLVEPRO_DEFAULT_STATE[key as keyof BuildEvolveproFormState]);
}

/** Seeds supported sample inputs into one project's form without overwriting user choices. */
export function seedBuildEvolveproForm(
  paths: Partial<Pick<
    BuildEvolveproFormState,
    | "activityPath"
    | "layoutXlsx"
    | "gcDataXlsx"
    | "round1ReportXlsx"
    | "remeasureReportXlsx"
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

  if (!current.activityPath) {
    if (paths.activityPath) next.primarySource = "longFormat";
    else if (paths.gcDataXlsx) next.primarySource = "gcSheet";
    else if (paths.round1ReportXlsx) next.primarySource = "rawReport";
  }
  if (
    current.confirmationSource === "none" &&
    !current.remeasureReportXlsx &&
    paths.remeasureReportXlsx
  ) {
    next.confirmationSource = "variantLabels";
  }
  saveBuildEvolveproToStorage(next, projectPath);
}
