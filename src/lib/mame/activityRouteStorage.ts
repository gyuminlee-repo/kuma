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

// "plateLayout", not "genotype", because only that route can currently produce
// a non-empty file.
//
// The genotype route joins the activity table against the round's NGS genotype,
// but nothing populates it: the sidecar round dict is lazy-created with
// round_id/n/status/plate_meta only (handlers/activity.py _get_round), no RPC
// writes `design` or `genotype`, and updateRoundField is called with
// plate_meta/activity/merged_table exclusively. So merge_activity_with_genotype
// receives two empty maps, every row falls to the activity_only branch with
// ngs_success=false, and export_evolvepro drops all of them. Measured through
// the handlers: n_with_genotype=0, n_ngs_success=0, written_rows=0. The export
// does report the exclusions, but no view surfaces them, so the route hands
// back a silently empty xlsx.
//
// Wiring the Analyze verdicts into the round is tracked separately; flipping
// this default back requires that work to land first.
export const ACTIVITY_ROUTE_DEFAULT: ActivityRoute = "plateLayout";

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
