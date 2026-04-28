import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import { createAnalysisSlice } from "./slices/analysisSlice";
import { createExportSlice } from "./slices/exportSlice";
import { createInputSlice } from "./slices/inputSlice";
import type { AppState } from "./types";
export type { AppState };

export const useMameAppStore = create<AppState>()(
  subscribeWithSelector((...args) => ({
    ...createInputSlice(...args),
    ...createAnalysisSlice(...args),
    ...createExportSlice(...args),
  })),
);
