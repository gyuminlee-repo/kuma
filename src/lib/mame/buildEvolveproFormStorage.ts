/**
 * buildEvolveproFormStorage.ts - BuildEvolveproInputPanel form state
 * localStorage read/write and sample path seed helpers.
 *
 * Extracted into a separate module so both the panel component and
 * analysisSlice can import it without creating a circular dependency.
 */

export const BUILD_EVOLVEPRO_STORAGE_KEY = "kuma:mame:buildEvolvepro";

export interface BuildEvolveproFormState {
  layoutXlsx: string;
  gcDataXlsx: string;
  repBatchXlsx: string;
  prevEvolveproXlsx: string;
  outputXlsx: string;
}

export const BUILD_EVOLVEPRO_DEFAULT_STATE: BuildEvolveproFormState = {
  layoutXlsx: "",
  gcDataXlsx: "",
  repBatchXlsx: "",
  prevEvolveproXlsx: "",
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
    return {
      layoutXlsx: typeof p.layoutXlsx === "string" ? p.layoutXlsx : "",
      gcDataXlsx: typeof p.gcDataXlsx === "string" ? p.gcDataXlsx : "",
      repBatchXlsx: typeof p.repBatchXlsx === "string" ? p.repBatchXlsx : "",
      prevEvolveproXlsx:
        typeof p.prevEvolveproXlsx === "string" ? p.prevEvolveproXlsx : "",
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
 */
export function seedBuildEvolveproForm(paths: {
  layoutXlsx?: string;
  gcDataXlsx?: string;
  repBatchXlsx?: string;
  prevEvolveproXlsx?: string;
}): void {
  const current = loadBuildEvolveproFromStorage();
  const next: BuildEvolveproFormState = {
    layoutXlsx: current.layoutXlsx || paths.layoutXlsx || "",
    gcDataXlsx: current.gcDataXlsx || paths.gcDataXlsx || "",
    repBatchXlsx: current.repBatchXlsx || paths.repBatchXlsx || "",
    prevEvolveproXlsx: current.prevEvolveproXlsx || paths.prevEvolveproXlsx || "",
    outputXlsx: current.outputXlsx,
  };
  saveBuildEvolveproToStorage(next);
}
