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
import type { JanusExportFormat, JanusExportResult } from "@/types/mame/models";

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
 * @returns           Resolved output path and format from sidecar.
 */
export async function handleExportMameJanusMapping(
  outputPath: string,
  format: JanusExportFormat = "csv",
): Promise<JanusExportResult> {
  useMameAppStore.setState({ isExporting: true });
  try {
    return await sendRequest<JanusExportResult>("export_janus_mapping", {
      output: outputPath,
      format,
    });
  } finally {
    useMameAppStore.setState({ isExporting: false });
  }
}
