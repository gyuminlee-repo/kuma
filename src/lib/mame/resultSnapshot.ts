/**
 * resultSnapshot.ts - MAME analyze-result persistence (Phase 2).
 *
 * The analyze input snapshot (`.autosave/mame.json`) is debounced and excludes
 * result fields. This module persists the FULL analyze RPC response AS-IS to a
 * SEPARATE sibling file (`.autosave/mame-result.json`), written ONCE on analyze
 * success (not on debounced input autosave). On restart, hydration reads it,
 * re-injects the payload into the sidecar via `load_analyze_result`, and lands
 * the user on the 2.2 review view.
 *
 * The persisted payload is the analyze response verbatim, including
 * `replicates[].plate_verdicts`, the ONLY lossless source for per-plate accent
 * (selected / is_fallback) restoration. Reconstructing from the reduced store
 * projection (`plate_keys` only) silently corrupts well flags.
 */

import { exists, readTextFile, rename } from "@tauri-apps/plugin-fs";
import { ensureAutosaveDir, atomicWriteJson } from "@/lib/autosave";
import type { AnalyzeResult } from "@/types/mame/models";

/** Result snapshot schema. Bumped independently of the input snapshot schema. */
export const MAME_RESULT_SCHEMA = 1;

const RESULT_FILE_NAME = "mame-result.json";

/** OS path join (Tauri IPC accepts absolute paths as-is; normalise on `/`). */
function joinPath(...segments: string[]): string {
  return segments
    .map((s, i) => (i === 0 ? s.replace(/[/\\]+$/, "") : s.replace(/^[/\\]+/, "")))
    .join("/");
}

/** `.autosave/mame-result.json` sibling of the input autosave snapshot. */
export function mameResultPath(projectPath: string): string {
  return joinPath(projectPath, ".autosave", RESULT_FILE_NAME);
}

/**
 * Persisted result file shape: the analyze response verbatim under `result`,
 * wrapped with schema / save metadata.
 */
export interface MameResultSnapshot {
  schema: typeof MAME_RESULT_SCHEMA;
  saved_at: string; // ISO8601
  kuma_version: string;
  result: AnalyzeResult;
}

/**
 * Write the analyze response AS-IS to the sibling result file. One-time on
 * analyze success, NOT debounced. Caller should `await` so an immediate
 * app-close does not lose the result. Silent no-op when projectPath is null
 * (scratch project).
 */
export async function writeMameResultSnapshot(
  projectPath: string | null,
  result: AnalyzeResult,
): Promise<void> {
  if (!projectPath) return;
  await ensureAutosaveDir(projectPath);
  const snapshot: MameResultSnapshot = {
    schema: MAME_RESULT_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    result,
  };
  await atomicWriteJson(mameResultPath(projectPath), snapshot);
}

export type ReadMameResultResult =
  | { status: "ok"; snapshot: MameResultSnapshot }
  | { status: "missing" };

/**
 * Read the sibling result file. Missing or unparseable -> `missing` (silent
 * skip in hydration). Corrupted files are renamed aside so a later analyze can
 * rewrite cleanly without colliding with a bad file.
 */
export async function readMameResultSnapshot(
  projectPath: string,
): Promise<ReadMameResultResult> {
  const filePath = mameResultPath(projectPath);
  if (!(await exists(filePath))) return { status: "missing" };

  let text: string;
  try {
    text = await readTextFile(filePath);
  } catch {
    return { status: "missing" };
  }

  let parsed: MameResultSnapshot;
  try {
    parsed = JSON.parse(text) as MameResultSnapshot;
  } catch {
    const isoTs = new Date().toISOString().replace(/[:.]/g, "-");
    try {
      await rename(filePath, `${filePath}.bad-${isoTs}`);
    } catch {
      console.warn(`[mame-result] failed to rename corrupted file: ${filePath}`);
    }
    return { status: "missing" };
  }

  if (parsed.schema > MAME_RESULT_SCHEMA || !parsed.result) {
    return { status: "missing" };
  }
  return { status: "ok", snapshot: parsed };
}
