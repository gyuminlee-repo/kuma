/**
 * buildEvolveproFormStorage.ts - BuildEvolveproInputPanel form state
 * localStorage read/write and sample path seed helpers.
 *
 * Extracted into a separate module so both the panel component and
 * analysisSlice can import it without creating a circular dependency.
 */

// v2: reports-mode fields (round1 + remeasure). Old v1 key left untouched so
// stale rank-mode paths never leak into the new fields.
export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro:v2";

export interface BuildEvolveproFormState {
  layoutXlsx: string;
  round1ReportXlsx: string;
  remeasureReportXlsx: string;
  outputXlsx: string;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  layoutXlsx: "",
  round1ReportXlsx: "",
  remeasureReportXlsx: "",
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
    // Merge known string keys over the default; stale keys are dropped silently.
    return {
      layoutXlsx: typeof p.layoutXlsx === "string" ? p.layoutXlsx : "",
      round1ReportXlsx:
        typeof p.round1ReportXlsx === "string" ? p.round1ReportXlsx : "",
      remeasureReportXlsx:
        typeof p.remeasureReportXlsx === "string" ? p.remeasureReportXlsx : "",
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

/**
 * Seeds sample paths into the localStorage form state.
 * Fields that are already filled are NOT overwritten (preserves user selections).
 * Called from analysisSlice.loadSampleData after sample resources are resolved.
 *
 * Only the layout path is seeded: reports-mode (round1/remeasure) raw reports
 * are not resolvable sample resources yet, so the legacy rank-mode params
 * (gcDataXlsx/repBatchXlsx/prevEvolveproXlsx) are accepted but ignored. This
 * keeps the analysisSlice caller unchanged until reports-mode sample seeding
 * lands in a later PR.
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
  };
  saveBuildEvolveproToStorage(next);
}
