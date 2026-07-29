/**
 * buildEvolveproFormStorage.ts - BuildEvolveproInputPanel form state
 * localStorage read/write and sample path seed helpers.
 *
 * Extracted into a separate module so both the panel component and
 * analysisSlice can import it without creating a circular dependency.
 */

export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro";

/**
 * Axis A, what carries the 1-replicate primary screen. Exactly one is sent to
 * the backend (round1_report_xlsx / gc_data_xlsx / round1_evolvepro_xlsx).
 */
export type BuildEvolveproPrimarySource =
  | "rawReport"
  | "gcSheet"
  | "prevEvolvepro";

/**
 * Axis B, how the n-replicate confirmation labels its samples. At most one is
 * sent (remeasure_report_xlsx / rep_batch_xlsx). "none" yields a provisional
 * build in which every variant keeps its primary screen value.
 */
export type BuildEvolveproConfirmationSource =
  | "none"
  | "variantLabels"
  | "numericIndex";

const PRIMARY_SOURCES: readonly BuildEvolveproPrimarySource[] = [
  "rawReport",
  "gcSheet",
  "prevEvolvepro",
];

const CONFIRMATION_SOURCES: readonly BuildEvolveproConfirmationSource[] = [
  "none",
  "variantLabels",
  "numericIndex",
];

export interface BuildEvolveproFormState {
  primarySource: BuildEvolveproPrimarySource;
  confirmationSource: BuildEvolveproConfirmationSource;
  layoutXlsx: string;
  gcDataXlsx: string;
  repBatchXlsx: string;
  prevEvolveproXlsx: string;
  round1ReportXlsx: string;
  round1EvolveproXlsx: string;
  remeasureReportXlsx: string;
  verdictXlsx: string;
  outputXlsx: string;
  /** Optional reports-mode raw round-1 export path (well-level relative
   *  activity, Sample Name / Area). Empty means no export. */
  gcExportXlsx: string;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  primarySource: "gcSheet",
  confirmationSource: "none",
  layoutXlsx: "",
  gcDataXlsx: "",
  repBatchXlsx: "",
  prevEvolveproXlsx: "",
  round1ReportXlsx: "",
  round1EvolveproXlsx: "",
  remeasureReportXlsx: "",
  verdictXlsx: "",
  outputXlsx: "",
  gcExportXlsx: "",
};

export function loadBuildEvolveproFromStorage(): BuildEvolveproFormState {
  try {
    const raw = localStorage.getItem(BUILD_EVOLVEPRO_STORAGE_KEY);
    if (!raw) return BUILD_EVOLVEPRO_DEFAULT_STATE;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null)
      return BUILD_EVOLVEPRO_DEFAULT_STATE;
    const p = parsed as Record<string, unknown>;
    // Payloads written before the two axes landed carry the single-toggle keys
    // (sourceMode / round1Source); migrateAxes maps them onto the axis pair so
    // saved paths and the selected combination both survive.
    return {
      ...migrateAxes(p),
      layoutXlsx: typeof p.layoutXlsx === "string" ? p.layoutXlsx : "",
      gcDataXlsx: typeof p.gcDataXlsx === "string" ? p.gcDataXlsx : "",
      repBatchXlsx: typeof p.repBatchXlsx === "string" ? p.repBatchXlsx : "",
      prevEvolveproXlsx:
        typeof p.prevEvolveproXlsx === "string" ? p.prevEvolveproXlsx : "",
      round1ReportXlsx:
        typeof p.round1ReportXlsx === "string" ? p.round1ReportXlsx : "",
      round1EvolveproXlsx:
        typeof p.round1EvolveproXlsx === "string" ? p.round1EvolveproXlsx : "",
      remeasureReportXlsx:
        typeof p.remeasureReportXlsx === "string" ? p.remeasureReportXlsx : "",
      verdictXlsx: typeof p.verdictXlsx === "string" ? p.verdictXlsx : "",
      outputXlsx: typeof p.outputXlsx === "string" ? p.outputXlsx : "",
      gcExportXlsx: typeof p.gcExportXlsx === "string" ? p.gcExportXlsx : "",
    };
  } catch {
    return BUILD_EVOLVEPRO_DEFAULT_STATE;
  }
}

/**
 * Reads the axis pair out of a stored payload, falling back to the legacy
 * single "Activity source" toggle when the axis keys are absent.
 *
 * Legacy mapping:
 *   rank                    -> gcSheet primary; numericIndex confirmation when
 *                              both rank-mode confirmation files were chosen,
 *                              otherwise none.
 *   reports + round1 "raw"  -> rawReport primary, variantLabels confirmation.
 *   reports + round1 "prev" -> prevEvolvepro primary, variantLabels confirmation.
 */
function migrateAxes(p: Record<string, unknown>): {
  primarySource: BuildEvolveproPrimarySource;
  confirmationSource: BuildEvolveproConfirmationSource;
} {
  const storedPrimary = PRIMARY_SOURCES.find((v) => v === p.primarySource);
  const storedConfirmation = CONFIRMATION_SOURCES.find(
    (v) => v === p.confirmationSource,
  );
  if (storedPrimary && storedConfirmation) {
    return {
      primarySource: storedPrimary,
      confirmationSource: storedConfirmation,
    };
  }

  const legacyReports = p.sourceMode === "reports";
  const primarySource: BuildEvolveproPrimarySource = legacyReports
    ? p.round1Source === "raw"
      ? "rawReport"
      : "prevEvolvepro"
    : "gcSheet";
  const hadRankConfirmation =
    typeof p.repBatchXlsx === "string" &&
    p.repBatchXlsx !== "" &&
    typeof p.prevEvolveproXlsx === "string" &&
    p.prevEvolveproXlsx !== "";
  const confirmationSource: BuildEvolveproConfirmationSource = legacyReports
    ? "variantLabels"
    : hadRankConfirmation
      ? "numericIndex"
      : "none";

  return {
    primarySource: storedPrimary ?? primarySource,
    confirmationSource: storedConfirmation ?? confirmationSource,
  };
}

export function saveBuildEvolveproToStorage(
  state: BuildEvolveproFormState,
): void {
  try {
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify(state),
    );
  } catch {
    // ignore persistence failures
  }
}

/** Whether axis A has every file its selected source needs. */
export function hasBuildEvolveproPrimaryInputs(
  state: BuildEvolveproFormState,
): boolean {
  switch (state.primarySource) {
    case "rawReport":
      return Boolean(state.layoutXlsx && state.round1ReportXlsx);
    case "gcSheet":
      return Boolean(state.layoutXlsx && state.gcDataXlsx);
    case "prevEvolvepro":
      return Boolean(state.round1EvolveproXlsx);
  }
}

/** Whether axis B has every file its selected source needs ("none" needs none). */
export function hasBuildEvolveproConfirmationInputs(
  state: BuildEvolveproFormState,
): boolean {
  switch (state.confirmationSource) {
    case "none":
      return true;
    case "variantLabels":
      return Boolean(state.remeasureReportXlsx);
    case "numericIndex":
      return Boolean(state.repBatchXlsx && state.prevEvolveproXlsx);
  }
}

export function isBuildEvolveproFormReady(
  state: BuildEvolveproFormState,
): boolean {
  if (!state.outputXlsx) return false;
  return (
    hasBuildEvolveproPrimaryInputs(state) &&
    hasBuildEvolveproConfirmationInputs(state)
  );
}

export interface BuildEvolveproCompletionRecord {
  outputPath: string;
  signature: string;
}

export function buildEvolveproFormSignature(
  state: BuildEvolveproFormState,
): string {
  return JSON.stringify({
    primarySource: state.primarySource,
    confirmationSource: state.confirmationSource,
    layoutXlsx: state.layoutXlsx,
    gcDataXlsx: state.gcDataXlsx,
    repBatchXlsx: state.repBatchXlsx,
    prevEvolveproXlsx: state.prevEvolveproXlsx,
    round1ReportXlsx: state.round1ReportXlsx,
    round1EvolveproXlsx: state.round1EvolveproXlsx,
    remeasureReportXlsx: state.remeasureReportXlsx,
    verdictXlsx: state.verdictXlsx,
    outputXlsx: state.outputXlsx,
  });
}

export function createBuildEvolveproCompletion(
  state: BuildEvolveproFormState,
  outputPath: string,
): BuildEvolveproCompletionRecord {
  return {
    outputPath,
    signature: buildEvolveproFormSignature(state),
  };
}

export function hasCompletedBuildEvolveproOutput(
  state: BuildEvolveproFormState,
  completion: BuildEvolveproCompletionRecord | null,
): boolean {
  if (!isBuildEvolveproFormReady(state)) return false;
  return (
    completion?.outputPath === state.outputXlsx &&
    completion.signature === buildEvolveproFormSignature(state)
  );
}

export function hasBuildEvolveproFormValues(
  state: BuildEvolveproFormState,
): boolean {
  return (
    state.primarySource !== BUILD_EVOLVEPRO_DEFAULT_STATE.primarySource ||
    state.confirmationSource !==
      BUILD_EVOLVEPRO_DEFAULT_STATE.confirmationSource ||
    Boolean(
      state.layoutXlsx ||
        state.gcDataXlsx ||
        state.repBatchXlsx ||
        state.prevEvolveproXlsx ||
        state.round1ReportXlsx ||
        state.round1EvolveproXlsx ||
        state.remeasureReportXlsx ||
        state.verdictXlsx ||
        state.outputXlsx,
    )
  );
}

/**
 * Seeds sample paths into the localStorage form state.
 * Fields that are already filled are NOT overwritten (preserves user selections).
 * Called from analysisSlice.loadSampleData after sample resources are resolved.
 */
export function seedBuildEvolveproForm(paths: {
  layoutXlsx?: string;
  gcDataXlsx?: string;
  repBatchXlsx?: string;
  prevEvolveproXlsx?: string;
}): void {
  const current = loadBuildEvolveproFromStorage();
  const next: BuildEvolveproFormState = {
    ...current,
    layoutXlsx: current.layoutXlsx || paths.layoutXlsx || "",
    gcDataXlsx: current.gcDataXlsx || paths.gcDataXlsx || "",
    repBatchXlsx: current.repBatchXlsx || paths.repBatchXlsx || "",
    prevEvolveproXlsx: current.prevEvolveproXlsx || paths.prevEvolveproXlsx || "",
    outputXlsx: current.outputXlsx,
  };
  // The sample set is a GC data sheet plus a numeric-index confirmation pair.
  // Select that axis B so the seeded rank files are visible rather than parked
  // behind a hidden branch, but never override a choice the user already made.
  if (
    next.confirmationSource === "none" &&
    next.repBatchXlsx &&
    next.prevEvolveproXlsx
  ) {
    next.confirmationSource = "numericIndex";
  }
  saveBuildEvolveproToStorage(next);
}
