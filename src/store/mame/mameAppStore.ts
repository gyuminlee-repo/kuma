import { create } from "zustand";
import { createAnalysisSlice } from "./slices/analysisSlice";
import { createExportSlice } from "./slices/exportSlice";
import { createInputSlice } from "./slices/inputSlice";
import type { AppState } from "./types";
export type { AppState };

export const useAppStore = create<AppState>()((...args) => {
  return {
    ...createInputSlice(...args),
    ...createAnalysisSlice(...args),
    ...createExportSlice(...args),
  };
});
