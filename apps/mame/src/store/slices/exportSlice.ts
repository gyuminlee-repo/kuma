import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import { formatError } from "../../lib/utils";
import type { ExportResult } from "../../types/models";
import type { ExportSlice } from "../slice-interfaces";
import type { AppState } from "../types";

export const createExportSlice: StateCreator<AppState, [], [], ExportSlice> = (set, get) => ({
  lastExportPath: null,
  lastExportAt: null,
  isExporting: false,
  exportError: null,
  exportExcel: async (path) => {
    set({ isExporting: true, exportError: null });
    try {
      const result = await sendRequest<ExportResult>("export_excel", {
        output: path,
        mode: get().mode,
      });
      set({
        lastExportPath: result.output_path,
        lastExportAt: new Date().toISOString(),
        isExporting: false,
      });
      get().setOutputPath(result.output_path);
    } catch (error) {
      set({
        exportError: formatError(error),
        isExporting: false,
      });
      throw error;
    }
  },
});
