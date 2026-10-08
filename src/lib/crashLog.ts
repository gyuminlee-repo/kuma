/**
 * Frontend crash log stored in localStorage.
 * FIFO buffer capped at 50 entries.
 */

const STORAGE_KEY = "kuro_crash_log";
const MAX_ENTRIES = 50;

export interface CrashEntry {
  timestamp: string;
  component: string;
  message: string;
  stack?: string;
}

function isCrashEntry(value: unknown): value is CrashEntry {
  if (typeof value !== "object" || value === null) return false;
  if (!("timestamp" in value) || !("component" in value) || !("message" in value)) {
    return false;
  }
  return (
    typeof value.timestamp === "string" &&
    typeof value.component === "string" &&
    typeof value.message === "string" &&
    (!("stack" in value) || value.stack === undefined || typeof value.stack === "string")
  );
}

export function appendCrashLog(entry: Omit<CrashEntry, "timestamp">): void {
  const log = getCrashLog();
  log.push({
    ...entry,
    timestamp: new Date().toISOString(),
  });
  // FIFO: keep only the newest MAX_ENTRIES
  while (log.length > MAX_ENTRIES) {
    log.shift();
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(log));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function getCrashLog(): CrashEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isCrashEntry) : [];
  } catch {
    return [];
  }
}
