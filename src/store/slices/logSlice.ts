/**
 * §2 Observability — Log Slice
 *
 * Accumulates progress message strings from the sidecar (via progress
 * notifications) as a rolling log buffer capped at MAX_LOG_LINES entries.
 *
 * Source: appStore.ts feeds each progress.message into appendLogLine.
 * Consumer: LogPanel.tsx renders the lines in real time.
 *
 * §D3.5: logPanelVisible / jobsPanelVisible 상태를 store로 lift up.
 * MainShell local state에서 이관. MenuBar View 메뉴와 MainShell이 공유.
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";

const MAX_LOG_LINES = 200;

const LOG_PANEL_VISIBLE_KEY = "kuma:floating-panel:log:visible";
const JOBS_PANEL_VISIBLE_KEY = "kuma:floating-panel:jobs:visible";

function readStoredVisible(key: string): boolean {
  if (typeof window === "undefined") return true;
  const raw = window.localStorage.getItem(key);
  return raw === null ? true : raw === "true";
}

export interface LogSlice {
  /** Rolling buffer of log lines (newest last), capped at 200 entries */
  logLines: string[];
  /** Append a new log line; automatically trims to MAX_LOG_LINES */
  appendLogLine: (line: string) => void;
  /** Clear all log lines */
  clearLogLines: () => void;
  /** Log panel visibility (persisted to localStorage) */
  logPanelVisible: boolean;
  setLogPanelVisible: (visible: boolean) => void;
  toggleLogPanel: () => void;
  /** Jobs panel visibility (persisted to localStorage) */
  jobsPanelVisible: boolean;
  setJobsPanelVisible: (visible: boolean) => void;
  toggleJobsPanel: () => void;
}

export const createLogSlice: StateCreator<AppState, [], [], LogSlice> = (
  set,
  get,
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

  logPanelVisible: readStoredVisible(LOG_PANEL_VISIBLE_KEY),
  setLogPanelVisible: (visible: boolean) => {
    window.localStorage.setItem(LOG_PANEL_VISIBLE_KEY, String(visible));
    set({ logPanelVisible: visible });
  },
  toggleLogPanel: () => {
    const next = !get().logPanelVisible;
    window.localStorage.setItem(LOG_PANEL_VISIBLE_KEY, String(next));
    set({ logPanelVisible: next });
  },

  jobsPanelVisible: readStoredVisible(JOBS_PANEL_VISIBLE_KEY),
  setJobsPanelVisible: (visible: boolean) => {
    window.localStorage.setItem(JOBS_PANEL_VISIBLE_KEY, String(visible));
    set({ jobsPanelVisible: visible });
  },
  toggleJobsPanel: () => {
    const next = !get().jobsPanelVisible;
    window.localStorage.setItem(JOBS_PANEL_VISIBLE_KEY, String(next));
    set({ jobsPanelVisible: next });
  },
});
