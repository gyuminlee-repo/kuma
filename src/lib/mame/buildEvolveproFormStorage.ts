/**
 * buildEvolveproFormStorage.ts - BuildEvolveproInputPanel form state
 * localStorage read/write and sample path seed helpers.
 *
 * Extracted into a separate module so both the panel component and
 * analysisSlice can import it without creating a circular dependency.
 */

export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro";

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
  /** Optional reports-mode raw round-1 export path (well-level relative
   *  activity, Sample Name / Area). Empty means no export. */
  gcExportXlsx: string;
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
      gcExportXlsx: typeof p.gcExportXlsx === "string" ? p.gcExportXlsx : "",
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
