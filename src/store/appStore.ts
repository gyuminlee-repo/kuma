import { create } from "zustand";
import { setProgressHandler } from "../lib/ipc-kuro";
import { createSequenceSlice } from "./slices/sequenceSlice";
import { createDiversitySlice } from "./slices/diversitySlice";
import { createInputSlice } from "./slices/inputSlice";
import { createDesignSlice } from "./slices/designSlice";
import { createExportSlice } from "./slices/exportSlice";
import { createNetworkConsentSlice } from "./slices/networkConsentSlice";
import type { AppState } from "./types";
export type { AppState };

export const useAppStore = create<AppState>()((...a) => {
  const [set] = a;

  setProgressHandler((p) => {
    set({ progress: p.value, statusMessage: p.message });
  });

  return {
    ...createSequenceSlice(...a),
    ...createDiversitySlice(...a),
    ...createInputSlice(...a),
    ...createDesignSlice(...a),
    ...createExportSlice(...a),
    ...createNetworkConsentSlice(...a),
  };
});
