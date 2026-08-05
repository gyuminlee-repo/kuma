/**
 * verdictColumnWidthStorage.ts - Verdict table column width persistence.
 *
 * Column widths are a per-machine view preference, not run data: they must not
 * travel inside a saved workspace, and they must outlive a reload (a width the
 * user has to drag again on every visit is worse than no resizing at all). That
 * is the same shape as react-resizable-panels `autoSaveId`
 * (AnalyzeStepView PanelGroup), which also keeps layout in localStorage rather
 * than in the app store, so this follows the existing
 * `*Storage.ts` read/write convention (buildEvolveproFormStorage.ts) instead of
 * adding view state to the MAME store.
 */

export const VERDICT_COLUMN_WIDTH_STORAGE_KEY = "kuma:mame:verdictColumnWidths";

/** Resize bounds (px). Below MIN a column becomes unreadable and unclickable. */
export const MIN_COLUMN_WIDTH = 56;
export const MAX_COLUMN_WIDTH = 900;

export type VerdictColumnWidths = Record<string, number>;

function isValidWidth(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= MIN_COLUMN_WIDTH &&
    value <= MAX_COLUMN_WIDTH
  );
}

/** Reads persisted widths, dropping any entry that is not a sane number. */
export function loadVerdictColumnWidths(): VerdictColumnWidths {
  try {
    const raw = localStorage.getItem(VERDICT_COLUMN_WIDTH_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
    const out: VerdictColumnWidths = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (isValidWidth(value)) out[key] = value;
    }
    return out;
  } catch {
    return {};
  }
}

export function saveVerdictColumnWidths(widths: VerdictColumnWidths): void {
  try {
    localStorage.setItem(VERDICT_COLUMN_WIDTH_STORAGE_KEY, JSON.stringify(widths));
  } catch {
    // ignore persistence failures
  }
}

/** Clamps a candidate width into the resize bounds. */
export function clampColumnWidth(width: number): number {
  return Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, width));
}
