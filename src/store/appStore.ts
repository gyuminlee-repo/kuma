import { create } from "zustand";
import { setProgressHandler } from "../lib/ipc-kuro";
import { createSequenceSlice } from "./slices/sequenceSlice";
import { createDiversitySlice } from "./slices/diversitySlice";
import { createInputSlice } from "./slices/inputSlice";
import { createDesignSlice } from "./slices/designSlice";
import { createExportSlice } from "./slices/exportSlice";
import { createNetworkConsentSlice } from "./slices/networkConsentSlice";
import { createMemorySlice } from "./slices/memorySlice";
import type { AppState } from "./types";
export type { AppState };

export const useAppStore = create<AppState>()((...a) => {
  const [set] = a;

  setProgressHandler((p) => {
    // §19 memory_warning notifications arrive as type="memory_warning" in params.
    // Cast to check for the discriminating field without broadening the handler type.
    const raw = p as unknown as Record<string, unknown>;
    if (raw["type"] === "memory_warning") {
      const ratio = typeof raw["ratio"] === "number" ? raw["ratio"] : 0;
      const rss_mb = typeof raw["rss_mb"] === "number" ? raw["rss_mb"] : 0;
      const level = raw["level"] === "block" ? "block" : "warn";
      set({ memoryWarning: { ratio, rss_mb, level } });
      return;
    }
    set({ progress: p.value, statusMessage: p.message });
  });

  return {
    ...createSequenceSlice(...a),
    ...createDiversitySlice(...a),
    ...createInputSlice(...a),
    ...createDesignSlice(...a),
    ...createExportSlice(...a),
    ...createNetworkConsentSlice(...a),
    ...createMemorySlice(...a),
  };
});
