/**
 * layoutStore.ts
 *
 * Standalone Zustand store for sidebar layout state, shared by both kuro and
 * mame without inject into their respective appStore / mameAppStore.
 *
 * This avoids dual-persist contention: if both stores wrote to "kuma.layout.v1"
 * the second write would overwrite the first on every render cycle.
 *
 * Usage:
 *   import { useLayoutStore } from "@/store/layoutStore";
 *   const width = useLayoutStore(s => s.sidebarWidth ?? s.computedDefault);
 *
 * Persist strategy:
 *   - sidebarWidth: persisted (user preference)
 *   - computedDefault: NOT persisted (recalculated by build script each release)
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createLayoutSlice, type LayoutSlice } from "./slices/layoutSlice";

export type { LayoutSlice };

export const useLayoutStore = create<LayoutSlice>()(
  persist(createLayoutSlice, {
    name: "kuma.layout.v1",
    partialize: (s) => ({ sidebarWidth: s.sidebarWidth }),
  }),
);
