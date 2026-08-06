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
 * transfer is an experimental condition). The 70 µL here is the volume this lab
 * transfers for this run, given by the operator who runs the instrument, and it
 * stays editable in the Volume field of the mapping panel, whose row preview
 * shows the number the file will carry.
 *
 * `outputSchema` is fixed at "device9" in practice: the instrument reads the
 * 9-column sheet, so the panel offers no choice. The field stays because the
 * sidecar still takes it and the analyze run pins "legacy5" for the automatic
 * pick list, a different file from the one this policy writes.
 */
export const DEFAULT_JANUS_SETTINGS: JanusExportSettings = {
  destLayout: "compact",
  includeVerdicts: ["PASS"],
  includeFallback: false,
  outputSchema: "device9",
  volume: 70,
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
 *
 * Two stored values are promoted rather than merged, because a merge over the
 * defaults would leave a machine pinned to something the panel no longer offers
 * any way to change. Both promotions are written on a copy, never on
 * {@link DEFAULT_JANUS_SETTINGS}, which this function hands back by reference
 * when there is nothing stored.
 */
export function loadJanusSettings(): JanusExportSettings {
  try {
    const raw = localStorage.getItem(JANUS_SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_JANUS_SETTINGS;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return DEFAULT_JANUS_SETTINGS;
    const merged = { ...DEFAULT_JANUS_SETTINGS, ...(parsed as Partial<JanusExportSettings>) };

    // A stored 100 is the old shipped default, which the UI itself used to call
    // an assumption with no lab source, so it reads as never chosen rather than
    // as a decision. The lab asked for 70, and without this a machine that ran
    // the earlier build would keep writing 100 into the mapping file. Any other
    // number is an operator decision and survives untouched.
    if (merged.volume === 100) merged.volume = DEFAULT_JANUS_SETTINGS.volume;

    // The instrument reads the 9-column sheet, so the panel dropped the schema
    // choice. A machine that picked the 5-column kuma sheet before would
    // otherwise keep exporting it with no control left to switch back. The
    // 5-column file is not lost: the analyze run still writes the pick list in
    // that shape on its own.
    if (merged.outputSchema === "legacy5") {
      merged.outputSchema = DEFAULT_JANUS_SETTINGS.outputSchema;
    }

    return merged;
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

