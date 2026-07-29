/**
 * activityRouteStorage.ts - Activity phase input-route selection persistence.
 *
 * The Activity phase (Step 3) offers two mutually exclusive ways to produce
 * the EVOLVEpro input xlsx:
 *   - "genotype": long-format activity CSV/xlsx merged against the current
 *     round's NGS genotype (IngestSection + MergeSection + ExportSection).
 *   - "plateLayout": plate layout + GC data xlsx files fed directly into
 *     mame.activity.build_evolvepro_input (BuildEvolveproInputPanel).
 *
 * Follows the same read/write pattern as buildEvolveproFormStorage.ts so the
 * selection survives a reload without touching the round/app store.
 */

export const ACTIVITY_ROUTE_STORAGE_KEY = "kuma:mame:activityRoute";

export type ActivityRoute = "genotype" | "plateLayout";

export const ACTIVITY_ROUTE_DEFAULT: ActivityRoute = "genotype";

function isActivityRoute(value: unknown): value is ActivityRoute {
  return value === "genotype" || value === "plateLayout";
}

export function loadActivityRouteFromStorage(): ActivityRoute {
  try {
    const raw = localStorage.getItem(ACTIVITY_ROUTE_STORAGE_KEY);
    if (!raw) return ACTIVITY_ROUTE_DEFAULT;
    const parsed: unknown = JSON.parse(raw);
    return isActivityRoute(parsed) ? parsed : ACTIVITY_ROUTE_DEFAULT;
  } catch {
    return ACTIVITY_ROUTE_DEFAULT;
  }
}

export function saveActivityRouteToStorage(route: ActivityRoute): void {
  try {
    localStorage.setItem(ACTIVITY_ROUTE_STORAGE_KEY, JSON.stringify(route));
  } catch {
    // ignore persistence failures
  }
}
