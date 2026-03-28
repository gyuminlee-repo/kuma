import { create } from "zustand";
import { setProgressHandler } from "../lib/ipc";
import { createInputSlice } from "./slices/inputSlice";
import { createDesignSlice } from "./slices/designSlice";
import { createExportSlice } from "./slices/exportSlice";
import type { AppState } from "./types";
export type { AppState };

export const useAppStore = create<AppState>()((...a) => {
  const [set] = a;

  setProgressHandler((p) => {
    set({ progress: p.value, statusMessage: p.message });
  });

  return {
    ...createInputSlice(...a),
    ...createDesignSlice(...a),
    ...createExportSlice(...a),
  };
});
