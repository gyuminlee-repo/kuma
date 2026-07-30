/**
 * Janus mapping export helpers for mame (K4 spec).
 *
 * Calls the sidecar `export_janus_mapping` RPC and resolves a default
 * output path based on the active project folder.
 *
 * G6/A6: priority_score now reflects read_count when available; falls back to
 * file_size_kb as a volume proxy. Column name priority_score is preserved for
 * downstream Janus consumers regardless of the underlying metric.
 */

import { sendRequest } from "@/lib/ipc-mame";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type {
  JanusExportFormat,
  JanusExportResult,
  JanusExportSettings,
  JanusPreviewResult,
} from "@/types/mame/models";

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
  sourceRacks: { P1: 1, P2: 2, P3: 3 },
  destRack: 4,
};

/**
 * Convert the UI settings into RPC params.
 *
 * The single conversion point for both the export and the preview, so the plate
 * the operator approves is the plate the exported file describes.
 */
function toRpcParams(settings: JanusExportSettings): Record<string, unknown> {
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

/**
 * Build the default Janus output path for a given project directory.
 *
 * Pattern: `<projectDir>/<projectName>_<YYYYMMDD>.mame.janus.<format>`
 */
export function buildJanusDefaultPath(
  projectDir: string,
  projectName: string,
  format: JanusExportFormat,
): string {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  const datestamp = `${yyyy}${mm}${dd}`;

  // Normalize separator: use forward slash for cross-platform paths.
  const dir = projectDir.replace(/\\/g, "/").replace(/\/$/, "");
  const safeName = projectName.replace(/[^a-zA-Z0-9_\-]/g, "_");

  return `${dir}/${safeName}_${datestamp}.mame.janus.${format}`;
}

/**
 * Export the Janus mapping via sidecar RPC.
 *
 * @param outputPath  Absolute path for the output file.
 * @param format      "csv" (default) or "xlsx".
 * @param settings    Selection and instrument policy. Defaults to
 *                    {@link DEFAULT_JANUS_SETTINGS}.
 * @returns           Resolved path, format, and the clones left out with the
 *                    reason for each.
 */
export async function handleExportMameJanusMapping(
  outputPath: string,
  format: JanusExportFormat = "csv",
  settings: JanusExportSettings = DEFAULT_JANUS_SETTINGS,
): Promise<JanusExportResult> {
  useMameAppStore.setState({ isExporting: true });
  try {
    return await sendRequest<JanusExportResult>("export_janus_mapping", {
      output: outputPath,
      format,
      ...toRpcParams(settings),
    });
  } finally {
    useMameAppStore.setState({ isExporting: false });
  }
}

/**
 * Preview the Janus mapping without writing a file.
 *
 * Calls the sidecar `export_janus_mapping_dry_run` RPC. Unlike the export, the
 * three plate-layout problems (unresolved well, over capacity, duplicate
 * destination) come back inside `errors` rather than as a thrown RPC error, so
 * the dialog can show all of them at once.
 *
 * `isExporting` is deliberately left alone: a preview is not an export and must
 * not put the app into its exporting state.
 *
 * The reply also carries the clones that would be left out, so the dialog can
 * show how many were dropped and why before a file is written.
 *
 * @param settings  Selection and instrument policy, identical to the one the
 *                  export will use. Defaults to {@link DEFAULT_JANUS_SETTINGS}.
 */
export async function fetchMameJanusPreview(
  settings: JanusExportSettings = DEFAULT_JANUS_SETTINGS,
): Promise<JanusPreviewResult> {
  return await sendRequest<JanusPreviewResult>(
    "export_janus_mapping_dry_run",
    toRpcParams(settings),
  );
}
