/**
 * buildEvolveproFormStorage.ts - BuildEvolveproInputPanel form state
 * localStorage read/write and sample path seed helpers.
 *
 * Extracted into a separate module so both the panel component and
 * analysisSlice can import it without creating a circular dependency.
 */

// v3: round-1 source toggle (prev EVOLVEpro file vs raw GC-FID report). Old v2
// key left untouched so stale paths never leak into the new fields.
export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro:v3";

/** Round-1 baseline source: a prior EVOLVEpro file (Variant/activity) or a raw
 *  GC-FID report (well-named) that needs the plate layout to map wells. */
export type Round1Source = "prev" | "raw";

export interface BuildEvolveproFormState {
  round1Source: Round1Source;
  layoutXlsx: string;
  round1ReportXlsx: string;
  round1EvolveproXlsx: string;
  remeasureReportXlsx: string;
  verdictXlsx: string;
  outputXlsx: string;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  round1Source: "prev",
  layoutXlsx: "",
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
    // Merge known keys over the default; stale keys are dropped silently.
    return {
      round1Source: p.round1Source === "raw" ? "raw" : "prev",
      layoutXlsx: typeof p.layoutXlsx === "string" ? p.layoutXlsx : "",
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
