/**
 * Janus policy: the defaults, the RPC shape, and where the operator's choice is
 * kept between sessions.
 *
 * Split out of `janus.ts` because that module imports the mame store, and the
 * store now reads these helpers back (the analyze call carries the settings).
 * Keeping the pure pieces store-free means no module-eval import cycle, a
 * failure this codebase has hit before.
 */

import type { JanusExportSettings } from "@/types/mame/models";

/**
 * Default export policy, mirroring ``JanusSettings``
 * (kuma_core/mame/export/janus_mapping.py).
 *
 * Hand-written, not generated, but no longer on trust:
 * `scripts/sync-check-janus-defaults.mjs` pushes these values through
 * {@link toRpcParams} and compares the result with `JanusSettings().to_payload()`,
 * and `pnpm sync:check` fails if either side moves alone. Editing a value here
 * means editing the matching constant there in the same change.
 *
 * Only fully verified clones ship: AMBIGUOUS carries a side indel that would
 * mislabel an activity measurement and LOWDEPTH is unverified, so both stay out
 * unless the operator opts in. A stock plate is a new plate, hence the compact
 * layout.
 *
 * Nothing here is asked of the operator except `volume`. `liquidClass` is
 * empty because it drives the pipetting behaviour of the robot and nothing may
 * guess it; the column simply ships blank and the preview warns. `sourceRacks`
 * is empty and `destRack` is null because the sidecar derives the deck from the
 * plates of the run, the way KURO already numbers this instrument.
 *
 * `volume` is the one value that cannot be derived (how much of a cell stock to
 * transfer is an experimental condition) and the 100 µL here is a stated
 * assumption with no lab source in this repository, which the UI says out loud.
 */
export const DEFAULT_JANUS_SETTINGS: JanusExportSettings = {
  destLayout: "compact",
  includeVerdicts: ["PASS"],
  includeFallback: false,
  outputSchema: "device9",
  volume: 100,
  sampleType: "cell",
  liquidClass: "",
  sourceRacks: {},
  destRack: null,
};

/**
 * Convert the UI settings into RPC params.
 *
 * The single conversion point for the export, the preview, and the mapping the
 * analyze run writes on its own (`janus_settings`), so the plate the operator
 * approves is the plate every one of those files describes.
 */
export function toRpcParams(settings: JanusExportSettings): Record<string, unknown> {
  return {
    dest_layout: settings.destLayout,
    include_verdicts: settings.includeVerdicts,
    include_fallback: settings.includeFallback,
    output_schema: settings.outputSchema,
    volume: settings.volume,
    sample_type: settings.sampleType,
    liquid_class: settings.liquidClass,
    source_racks: settings.sourceRacks,
    dest_rack: settings.destRack,
  };
}

/** Where the operator's Janus policy is kept between sessions. */
export const JANUS_SETTINGS_STORAGE_KEY = "kuma:mame:janusSettings";

/**
 * Read the stored Janus policy, falling back to {@link DEFAULT_JANUS_SETTINGS}.
 *
 * Persisted because an analyze run writes both files on its own: whatever the
 * operator set here (volume above all) has to still be in force at the next
 * session's first run, without reopening the dialog.
 * Unknown or malformed content is ignored rather than repaired; the defaults
 * are the safe reading.
 */
export function loadJanusSettings(): JanusExportSettings {
  try {
    const raw = localStorage.getItem(JANUS_SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_JANUS_SETTINGS;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return DEFAULT_JANUS_SETTINGS;
    return { ...DEFAULT_JANUS_SETTINGS, ...(parsed as Partial<JanusExportSettings>) };
  } catch {
    return DEFAULT_JANUS_SETTINGS;
  }
}

export function saveJanusSettings(settings: JanusExportSettings): void {
  try {
    localStorage.setItem(JANUS_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // ignore persistence failures
  }
}

