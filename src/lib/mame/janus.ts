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
  JanusDestLayout,
  JanusExportFormat,
  JanusExportResult,
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
 * @param destLayout  "source" (default, dest mirrors source well) or
 *                    "compact" (dest assigned sequentially from A1).
 * @returns           Resolved output path and format from sidecar.
 */
export async function handleExportMameJanusMapping(
  outputPath: string,
  format: JanusExportFormat = "csv",
  destLayout: JanusDestLayout = "source",
): Promise<JanusExportResult> {
  useMameAppStore.setState({ isExporting: true });
  try {
    return await sendRequest<JanusExportResult>("export_janus_mapping", {
      output: outputPath,
      format,
      dest_layout: destLayout,
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
 * @param destLayout  "source" (default, dest mirrors source well) or
 *                    "compact" (dest assigned sequentially from A1).
 */
export async function fetchMameJanusPreview(
  destLayout: JanusDestLayout = "source",
): Promise<JanusPreviewResult> {
  return await sendRequest<JanusPreviewResult>("export_janus_mapping_dry_run", {
    dest_layout: destLayout,
  });
}
