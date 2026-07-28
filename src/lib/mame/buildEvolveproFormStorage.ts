/**
 * buildEvolveproFormStorage.ts - BuildEvolveproInputPanel form state
 * localStorage read/write and sample path seed helpers.
 *
 * Extracted into a separate module so both the panel component and
 * analysisSlice can import it without creating a circular dependency.
 */

export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro";
export const BUILD_EVOLVEPRO_COMPLETION_KEY = "kuma:mame:buildEvolvepro:complete";

/** Which backend input mode the panel builds params for. */
export type BuildEvolveproSourceMode = "rank" | "reports";

/** Reports mode round-1 baseline source (exactly one is sent to the backend). */
export type BuildEvolveproRound1Source = "prev" | "raw";

export interface BuildEvolveproFormState {
  sourceMode: BuildEvolveproSourceMode;
  round1Source: BuildEvolveproRound1Source;
  layoutXlsx: string;
  gcDataXlsx: string;
  repBatchXlsx: string;
  prevEvolveproXlsx: string;
  round1ReportXlsx: string;
  round1EvolveproXlsx: string;
  remeasureReportXlsx: string;
  verdictXlsx: string;
  outputXlsx: string;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  sourceMode: "rank",
  round1Source: "prev",
  layoutXlsx: "",
  gcDataXlsx: "",
  repBatchXlsx: "",
  prevEvolveproXlsx: "",
  round1ReportXlsx: "",
  round1EvolveproXlsx: "",
  remeasureReportXlsx: "",
  verdictXlsx: "",
  outputXlsx: "",
};

export function loadBuildEvolveproFromStorage(): BuildEvolveproFormState {
  try {
    const raw = localStorage.getItem(BUILD_EVOLVEPRO_STORAGE_KEY);
    if (!raw) return BUILD_EVOLVEPRO_DEFAULT_STATE;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null)
      return BUILD_EVOLVEPRO_DEFAULT_STATE;
    const p = parsed as Record<string, unknown>;
    // Payloads written before the reports mode landed carry only the rank-mode
    // keys; the new fields fall back to their defaults so saved paths survive.
    return {
      sourceMode: p.sourceMode === "reports" ? "reports" : "rank",
      round1Source: p.round1Source === "raw" ? "raw" : "prev",
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
    };
  } catch {
    return BUILD_EVOLVEPRO_DEFAULT_STATE;
  }
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

export function isBuildEvolveproFormReady(
  state: BuildEvolveproFormState,
): boolean {
  if (!state.outputXlsx) return false;
  if (state.sourceMode === "rank") {
    return Boolean(state.layoutXlsx && state.gcDataXlsx);
  }
  if (state.round1Source === "prev") {
    return Boolean(state.round1EvolveproXlsx && state.remeasureReportXlsx);
  }
  return Boolean(
    state.layoutXlsx &&
      state.round1ReportXlsx &&
      state.remeasureReportXlsx,
  );
}

interface BuildEvolveproCompletionRecord {
  outputPath: string;
  signature: string;
}

function buildCompletionSignature(state: BuildEvolveproFormState): string {
  return JSON.stringify({
    sourceMode: state.sourceMode,
    round1Source: state.round1Source,
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

export function markBuildEvolveproComplete(
  state: BuildEvolveproFormState,
  outputPath: string,
): void {
  const record: BuildEvolveproCompletionRecord = {
    outputPath,
    signature: buildCompletionSignature(state),
  };
  try {
    localStorage.setItem(BUILD_EVOLVEPRO_COMPLETION_KEY, JSON.stringify(record));
  } catch {
  }
}

export function clearBuildEvolveproCompletion(): void {
  try {
    localStorage.removeItem(BUILD_EVOLVEPRO_COMPLETION_KEY);
  } catch {
  }
}

export function hasCompletedBuildEvolveproOutput(
  state: BuildEvolveproFormState,
): boolean {
  if (!isBuildEvolveproFormReady(state)) return false;
  try {
    const raw = localStorage.getItem(BUILD_EVOLVEPRO_COMPLETION_KEY);
    if (!raw) return false;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return false;
    const record = parsed as Partial<BuildEvolveproCompletionRecord>;
    return (
      record.outputPath === state.outputXlsx &&
      record.signature === buildCompletionSignature(state)
    );
  } catch {
    return false;
  }
}

export function hasBuildEvolveproFormValues(
  state: BuildEvolveproFormState,
): boolean {
  return (
    state.sourceMode !== BUILD_EVOLVEPRO_DEFAULT_STATE.sourceMode ||
    state.round1Source !== BUILD_EVOLVEPRO_DEFAULT_STATE.round1Source ||
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
  saveBuildEvolveproToStorage(next);
}
