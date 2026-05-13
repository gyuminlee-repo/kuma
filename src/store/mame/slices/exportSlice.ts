import type { StateCreator } from "zustand";
import { sendRequest } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import { registerArtifacts, getActiveWorkspace } from "@/lib/workspace";
import type { ExportResult } from "@/types/mame/models";
import type { ExportSlice } from "../slice-interfaces";
import type { AppState } from "../types";

const mameInitialExportState: Pick<
  ExportSlice,
  "lastExportPath" | "lastExportAt" | "isExporting" | "exportError"
> = {
  lastExportPath: null,
  lastExportAt: null,
  isExporting: false,
  exportError: null,
};

export const createExportSlice: StateCreator<AppState, [], [], ExportSlice> = (set, get) => ({
  ...mameInitialExportState,
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
      if (getActiveWorkspace()) {
        try {
          await registerArtifacts([
            {
              app: "mame",
              step: "analysis",
              type: "mame_consensus_fasta",
              absolutePath: result.output_path,
            },
          ]);
        } catch {
          // do not surface manifest failures to the user
        }
      }
    } catch (error) {
      set({
        exportError: formatError(error),
        isExporting: false,
      });
      throw error;
    }
  },
  resetExport: () => set({ ...mameInitialExportState }),
});
