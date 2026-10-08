/**
 * §16 Local Diagnostics — diagnostics bundle generator.
 *
 * Collects app meta, crash log, and recent log lines into a JSON file.
 * The file is written to a user-chosen path via save dialog.
 * No external data transmission — local file only (§16 [필수]).
 *
 * Returns the saved file path, or null if the user cancelled.
 */

import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import { getCrashLog } from "./crashLog";
import { useAppStore } from "@/store/appStore";

// Tauri global declared in vite-env.d.ts / via window.__APP_VERSION__
declare const __APP_VERSION__: string;

export interface DiagnosticsMeta {
  appVersion: string;
  generatedAt: string;
  userAgent: string;
  platform: string;
}

export interface DiagnosticsBundle {
  meta: DiagnosticsMeta;
  crashLog: ReturnType<typeof getCrashLog>;
  /** Most recent 50 lines from the sidecar log buffer */
  recentLogs: string[];
}

/**
 * Generate a diagnostics bundle and prompt the user to save it.
 *
 * Anonymisation policy:
 * - Only log *messages* are included (no file paths or user data from inputs).
 * - Crash log entries include component + message + optional stack; no user data.
 * - The bundle does NOT include mutation text, sequences, or file paths.
 *
 * @param logLines - Optional log buffer to include. When omitted, falls back to
 *   the kuro appStore logLines buffer (legacy). Pass an empty array for apps
 *   (e.g. mame) that have no sidecar log buffer.
 * @returns Saved file path, or null if the user cancelled the save dialog.
 */
export async function generateDiagnosticsBundle(
  logLines?: string[],
): Promise<string | null> {
  const meta: DiagnosticsMeta = {
    appVersion: __APP_VERSION__,
    generatedAt: new Date().toISOString(),
    userAgent: navigator.userAgent,
    platform: navigator.platform,
  };

  const crashLog = getCrashLog();

  // Take the most recent 50 lines from the provided buffer, or fall back to
  // the kuro appStore buffer for backward compatibility.
  const sourceLines = logLines ?? useAppStore.getState().logLines;
  const recentLogs = sourceLines.slice(-50);

  const bundle: DiagnosticsBundle = {
    meta,
    crashLog,
    recentLogs,
  };

  const defaultFilename = `kuma-diagnostics-${new Date().toISOString().slice(0, 10)}.json`;

  const filePath = await save({
    defaultPath: defaultFilename,
    filters: [{ name: "Diagnostics JSON", extensions: ["json"] }],
    title: "Save Diagnostics",
  });

  if (!filePath) return null;

  await writeTextFile(filePath, JSON.stringify(bundle, null, 2));

  return filePath;
}
