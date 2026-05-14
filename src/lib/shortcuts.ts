/**
 * Keyboard shortcut registry — single source of truth for kuro and mame.
 * Consumed by KeyboardShortcutsDialog, About dialog, and handler registrations.
 */

const isMac =
  typeof navigator !== "undefined" && navigator.userAgent.includes("Mac");

export const MOD = isMac ? "⌘" : "Ctrl";

export type ShortcutCategory = "file" | "edit" | "view" | "run" | "help";

export interface ShortcutEntry {
  keys: string;
  action: string;
  scope: "kuro" | "mame" | "both";
  category: ShortcutCategory;
}

export const SHORTCUTS: ShortcutEntry[] = [
  // File
  { keys: `${MOD}+O`,           action: "Open Sequence",          scope: "kuro", category: "file" },

  // Edit
  { keys: `${MOD}+,`,           action: "Preferences",            scope: "both", category: "edit" },

  // View
  { keys: `${MOD}+L`,           action: "Toggle Logs panel",      scope: "both", category: "view" },
  { keys: `${MOD}+J`,           action: "Toggle Jobs panel",      scope: "both", category: "view" },

  // Run
  { keys: `${MOD}+D`,           action: "Run / Analyze",          scope: "both", category: "run" },
  { keys: `${MOD}+Enter`,       action: "Run / Analyze (alias)",  scope: "both", category: "run" },
  { keys: `${MOD}+Shift+R`,     action: "Reset All",              scope: "both", category: "run" },

  // Help
  { keys: `${MOD}+/`,           action: "Keyboard shortcuts",     scope: "both", category: "help" },
];

/** Returns shortcuts visible to the given app scope. */
export function getShortcutsFor(scope: "kuro" | "mame"): ShortcutEntry[] {
  return SHORTCUTS.filter((s) => s.scope === scope || s.scope === "both");
}

/** Groups shortcuts by category for sectioned display. */
export function groupByCategory(
  entries: ShortcutEntry[],
): Record<ShortcutCategory, ShortcutEntry[]> {
  const groups: Record<ShortcutCategory, ShortcutEntry[]> = {
    file: [],
    edit: [],
    view: [],
    run: [],
    help: [],
  };
  for (const e of entries) groups[e.category].push(e);
  return groups;
}
