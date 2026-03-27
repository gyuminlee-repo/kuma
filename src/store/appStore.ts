import { create } from "zustand";
import { setProgressHandler } from "../lib/ipc";
import { createInputSlice, type InputSlice } from "./slices/inputSlice";
import { createDesignSlice, type DesignSlice } from "./slices/designSlice";
import { createExportSlice, type ExportSlice } from "./slices/exportSlice";

export type AppState = InputSlice & DesignSlice & ExportSlice;

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
