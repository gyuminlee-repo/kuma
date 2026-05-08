/**
 * Keyboard shortcut registry — single source of truth for kuro and mame.
 * Displayed in About dialogs and used as reference for handler registrations.
 */

const isMac =
  typeof navigator !== "undefined" && navigator.userAgent.includes("Mac");

export const MOD = isMac ? "⌘" : "Ctrl";

export interface ShortcutEntry {
  keys: string;
  action: string;
  scope: "kuro" | "mame" | "both";
}

export const SHORTCUTS: ShortcutEntry[] = [
  // Run shortcuts — Cmd/Ctrl+D is the primary; Enter is an alias
  { keys: `${MOD}+D`,           action: "Run / Analyze",          scope: "both" },
  { keys: `${MOD}+Enter`,       action: "Run / Analyze (alias)",  scope: "both" },
  { keys: `${MOD}+S`,           action: "Save Workspace",         scope: "both" },
  { keys: `${MOD}+O`,           action: "Open Workspace",         scope: "both" },
  { keys: `${MOD}+E`,           action: "Export Results",         scope: "both" },
  { keys: `${MOD}+Shift+R`,     action: "Reset All",              scope: "both" },
];

/** Returns shortcuts visible to the given app scope. */
export function getShortcutsFor(scope: "kuro" | "mame"): ShortcutEntry[] {
  return SHORTCUTS.filter((s) => s.scope === scope || s.scope === "both");
}
