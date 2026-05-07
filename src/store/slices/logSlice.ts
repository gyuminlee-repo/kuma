/**
 * §2 Observability — Log Slice
 *
 * Accumulates progress message strings from the sidecar (via progress
 * notifications) as a rolling log buffer capped at MAX_LOG_LINES entries.
 *
 * Source: appStore.ts feeds each progress.message into appendLogLine.
 * Consumer: LogPanel.tsx renders the lines in real time.
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";

const MAX_LOG_LINES = 200;

export interface LogSlice {
  /** Rolling buffer of log lines (newest last), capped at 200 entries */
  logLines: string[];
  /** Append a new log line; automatically trims to MAX_LOG_LINES */
  appendLogLine: (line: string) => void;
  /** Clear all log lines */
  clearLogLines: () => void;
}

export const createLogSlice: StateCreator<AppState, [], [], LogSlice> = (
  set,
) => ({
  logLines: [],

  appendLogLine: (line: string) => {
    if (!line.trim()) return;
    set((s) => {
      const next = [...s.logLines, line];
      if (next.length > MAX_LOG_LINES) {
        next.splice(0, next.length - MAX_LOG_LINES);
      }
      return { logLines: next };
    });
  },

  clearLogLines: () => {
    set({ logLines: [] });
  },
});
