/**
 * Run report export helpers for mame (A14 milestone).
 *
 * Calls the sidecar `export_run_report` RPC and resolves a default output
 * path based on the active project folder.
 */

import { sendRequest } from "@/lib/ipc-mame";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { RunReportFormat, RunReportResult } from "@/types/mame/models";

/**
 * Build the default run report output path for a given project directory.
 *
 * Pattern: `<projectDir>/<projectName>_<YYYYMMDD>.mame.report.<format>`
 */
export function buildRunReportDefaultPath(
  projectDir: string,
  projectName: string,
  format: RunReportFormat,
): string {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  const datestamp = `${yyyy}${mm}${dd}`;

  const dir = projectDir.replace(/\\/g, "/").replace(/\/$/, "");
  const safeName = projectName.replace(/[^a-zA-Z0-9_\-]/g, "_");

  return `${dir}/${safeName}_${datestamp}.mame.report.${format}`;
}

/**
 * Export the run report via sidecar RPC.
 *
 * @param outputPath   Absolute path for the output file.
 * @param format       "html" (default) or "pdf".
 * @param projectName  Optional project display name embedded in the report.
 */
export async function handleExportRunReport(
  outputPath: string,
  format: RunReportFormat = "html",
  projectName?: string,
): Promise<RunReportResult> {
  useMameAppStore.setState({ isExporting: true });
  try {
    return await sendRequest<RunReportResult>("export_run_report", {
      output: outputPath,
      format,
      project_name: projectName ?? null,
    });
  } finally {
    useMameAppStore.setState({ isExporting: false });
  }
}
