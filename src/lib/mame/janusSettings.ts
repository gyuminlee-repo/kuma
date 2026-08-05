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
 * Only fully verified clones ship: AMBIGUOUS carries a side indel that would
 * mislabel an activity measurement and LOWDEPTH is unverified, so both stay out
 * unless the operator opts in. A stock plate is a new plate, hence the compact
 * layout. `liquidClass` is deliberately empty: it drives the pipetting
 * behaviour of the robot, so the sidecar blocks the export until it is set.
 *
 * `volume`, `sampleType`, and the rack numbers are stated assumptions with no
 * lab source in this repository; the dialog surfaces them for editing.
 */
export const DEFAULT_JANUS_SETTINGS: JanusExportSettings = {
  destLayout: "compact",
  includeVerdicts: ["PASS"],
  includeFallback: false,
  outputSchema: "device9",
  volume: 100,
  sampleType: "cell",
  liquidClass: "",
  sourceRacks: { NB01: 1, NB02: 2, NB03: 3 },
  destRack: 4,
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
 * Persisted because an analyze run now writes the mapping on its own: without a
 * liquid class the sidecar refuses, so an operator who set one in the dialog
 * would otherwise have to set it again before every session's first run.
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

