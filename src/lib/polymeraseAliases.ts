/**
 * polymeraseAliases.ts, retired polymerase profile names and their replacements.
 *
 * Single source of truth for (a) the default profile used by fresh state and
 * reset, and (b) the alias map applied when a saved workspace or autosave
 * snapshot references a profile that no longer ships with the app.
 *
 * "Benchling" was removed in v0.13.20: it names the fixed design-time Tm scale
 * (SantaLucia 1998 via Benchling), not a real enzyme, so it never belonged in
 * the polymerase list. Saved states that selected it are mapped onto KOD.
 *
 * GC range and overlap mode are deliberately NOT rewritten by the alias: the
 * retired profile allowed GC 30-70 while KOD allows 40-60, so re-applying
 * profile defaults would silently change the design conditions of an old run.
 * Callers must set the resolved name without routing through
 * setSelectedPolymerase, which always overwrites GC and overlap mode.
 */

/** Profile selected by fresh state and by Reset. */
export const DEFAULT_POLYMERASE = "KOD";

/** Removed profile name → replacement profile name. */
export const RETIRED_POLYMERASE_ALIASES: Readonly<Record<string, string>> = {
  Benchling: DEFAULT_POLYMERASE,
};

export interface ResolvedPolymerase {
  /** Name to use going forward. */
  name: string;
  /** Original name when it was a retired profile, otherwise null. */
  retiredFrom: string | null;
}

/**
 * Map a possibly-retired profile name onto a surviving one.
 * Unknown names are returned unchanged with `retiredFrom: null` so that callers
 * can keep their own fallback behaviour for genuinely missing custom profiles.
 */
export function resolvePolymeraseName(name: string): ResolvedPolymerase {
  const replacement = RETIRED_POLYMERASE_ALIASES[name];
  return replacement ? { name: replacement, retiredFrom: name } : { name, retiredFrom: null };
}

/**
 * User-facing notice for a completed alias migration. Reports the removed
 * profile, its replacement, and the GC range that was preserved.
 */
export function retiredPolymeraseNotice(
  retiredFrom: string,
  replacement: string,
  gcMin: number,
  gcMax: number,
): string {
  return `Saved profile "${retiredFrom}" was removed; switched to ${replacement}. GC range kept at ${gcMin}-${gcMax}%.`;
}
