/**
 * layoutSlice.ts
 *
 * Zustand slice for sidebar layout state.
 * Used by the standalone useLayoutStore — NOT injected into appStore or
 * mameAppStore to avoid dual-persist contention on the same localStorage key
 * (spec §15.6, instruction §4).
 *
 * Persist key: "kuma.layout.v1"
 * Partial persist: sidebarWidth only (computedDefault is recalculated each build).
 */

import type { StateCreator } from "zustand";
import { SIDEBAR_DEFAULT_WIDTH } from "@/lib/sidebar-default-width";

export interface LayoutSlice {
  /** User-chosen width in px. null = use computedDefault. */
  sidebarWidth: number | null;
  /** Runtime-measured or build-time default. Never persisted. */
  computedDefault: number;
  setSidebarWidth: (w: number | null) => void;
  setComputedDefault: (w: number) => void;
}

export const createLayoutSlice: StateCreator<LayoutSlice> = (set) => ({
  sidebarWidth: null,
  computedDefault: SIDEBAR_DEFAULT_WIDTH,
  setSidebarWidth: (w) => set({ sidebarWidth: w }),
  setComputedDefault: (w) => set({ computedDefault: w }),
});
