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
import { DEFAULT_JANUS_SETTINGS, toRpcParams } from "./janusSettings";

// Re-exported so callers keep one import site for the Janus policy, while the
// definitions stay in a store-free module (see janusSettings.ts).
export {
  DEFAULT_JANUS_SETTINGS,
  JANUS_SETTINGS_STORAGE_KEY,
  loadJanusSettings,
  saveJanusSettings,
  toRpcParams,
} from "./janusSettings";
import type {
  JanusExportFormat,
  JanusExportResult,
  JanusExportSettings,
  JanusPreviewResult,
} from "@/types/mame/models";

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
