import type { StateCreator } from "zustand";
import { sendRequest } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import { registerArtifacts, ensureWorkspaceFromExportPath } from "@/lib/workspace";
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
      // Store the folder only; the full export path is tracked in lastExportPath.
      const exportDir = (() => {
        const p = result.output_path.replace(/\\/g, "/");
        const i = p.lastIndexOf("/");
        return i >= 0 ? result.output_path.slice(0, i) : result.output_path;
      })();
      get().setOutputPath(exportDir);
      try {
        await ensureWorkspaceFromExportPath(result.output_path);
        await registerArtifacts([
          {
            app: "mame",
            step: "analysis",
            type: "mame_consensus_fasta",
            absolutePath: result.output_path,
          },
        ]);
      } catch {
        // registry failure must not surface to the user
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
