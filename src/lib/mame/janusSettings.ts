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
 * Nothing here is asked of the operator except `volume`. `liquidClass` is empty
 * because it describes how the robot pipettes and nothing may guess it; it is
 * recorded with the run and written to no file, since the instrument sheet has
 * no column for it. `sourceRacks` is empty and `destRack` is null because the
 * sidecar generates the plate names from the plates of the run, and the panel
 * offers no way to name a plate by hand.
 *
 * `volume` is the one value that cannot be derived (how much of a cell stock to
 * transfer is an experimental condition). The 70 µL here is the volume this lab
 * transfers for this run, given by the operator who runs the instrument, and it
 * stays editable in the Volume field of the mapping panel, whose row preview
 * shows the number the file will carry.
 *
 * `outputSchema` is fixed at "device" in practice: the instrument reads that
 * sheet, so the panel offers no choice. The field stays because the sidecar
 * still takes it and the analyze run pins "legacy5" for the automatic pick
 * list, a different file from the one this policy writes.
 */
export const DEFAULT_JANUS_SETTINGS: JanusExportSettings = {
  destLayout: "compact",
  includeVerdicts: ["PASS"],
  includeFallback: false,
  outputSchema: "device",
  volume: 70,
  sampleType: "cell stock",
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
 * Several stored values are promoted rather than merged, because a merge over
 * the defaults would leave a machine pinned to something the panel no longer
 * offers any way to change, or to a value the lab has since replaced. Every
 * promotion is written on a copy, never on {@link DEFAULT_JANUS_SETTINGS},
 * which this function hands back by reference when there is nothing stored.
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

    // Same reading for a stored "cell": it is the old shipped default, and the
    // lab workbook writes "cell stock" in the type column of every row. Without
    // this, a machine that ever opened step 3 keeps writing the shorter word
    // and the change of default reaches nobody who already has the app. An
    // operator who typed something else is stating what the plate holds, so
    // that survives.
    if (merged.sampleType === "cell") {
      merged.sampleType = DEFAULT_JANUS_SETTINGS.sampleType;
    }

    // The instrument reads one sheet, so the panel dropped the schema choice. A
    // machine that picked the 5-column kuma sheet before would otherwise keep
    // exporting it with no control left to switch back. The 5-column file is
    // not lost: the analyze run still writes the pick list in that shape on its
    // own.
    if (merged.outputSchema === "legacy5") {
      merged.outputSchema = DEFAULT_JANUS_SETTINGS.outputSchema;
    }

    // The instrument schema was called "device9" while its sheet had nine
    // columns. The lab replaced that sheet with an eight column one, so the
    // count left the name. A machine that stored the old string would send it
    // on every export, and the sidecar validates the schema against a fixed
    // list, so the promotion has to happen here rather than being left to the
    // wire. The sidecar accepts the old string too, for a request already in
    // flight when the build changed under it. The cast is because the old value
    // is deliberately outside {@link JanusOutputSchema}: it is stored history,
    // not a schema the panel may write.
    if ((merged.outputSchema as string) === "device9") {
      merged.outputSchema = DEFAULT_JANUS_SETTINGS.outputSchema;
    }

    // A deck stored before the sheet named its plates holds rack NUMBERS,
    // because the panel used to ask for them. The two rack columns carry plate
    // names now, and a stored 1 is not a name that can be repaired into
    // "Stock plate1": as an override it would put a bare number where the robot
    // expects a labware name, and the panel has no field left to correct it in.
    // So numbers are dropped, which restores the generated names. A map that is
    // not a map of strings is discarded whole rather than filtered, because a
    // half-named deck describes no run.
    const storedRacks: unknown = merged.sourceRacks;
    const rackValues =
      storedRacks && typeof storedRacks === "object" ? Object.values(storedRacks) : null;
    if (rackValues === null || rackValues.some((value) => typeof value !== "string")) {
      merged.sourceRacks = DEFAULT_JANUS_SETTINGS.sourceRacks;
    }
    if (merged.destRack !== null && typeof merged.destRack !== "string") {
      merged.destRack = DEFAULT_JANUS_SETTINGS.destRack;
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

