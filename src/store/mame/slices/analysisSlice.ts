import { functionalUpdate } from "@tanstack/react-table";
import { resolveResource } from "@tauri-apps/api/path";
import type { StateCreator } from "zustand";
import { sendRequest } from "@/lib/ipc-mame";
import {
  sampleReplicates,
  sampleSummary,
  sampleVerdicts,
  sampleWells,
} from "@/lib/mame/sampleData";
import type { PlateDataResult, RunHealthData } from "@/types/mame/models";
import type { AnalysisSlice } from "../slice-interfaces";
import type { AppState } from "../types";

export const createAnalysisSlice: StateCreator<AppState, [], [], AnalysisSlice> = (
  set,
  get,
) => ({
  verdicts: [],
  replicates: [],
  summary: null,
  plateFilter: "ALL",
  searchQuery: "",
  sorting: [],
  showExport: false,
  wells: [],
  selectedWell: null,
  runHealth: null,
  setVerdicts: (verdicts) => set({ verdicts }),
  setReplicates: (replicates) => set({ replicates }),
  setSummary: (summary) => set({ summary }),
  setPlateFilter: (plateFilter) => set({ plateFilter }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSorting: (updater) => {
    const next = functionalUpdate(updater, get().sorting);
    set({ sorting: next });
  },
  openExport: () => set({ showExport: true }),
  closeExport: () => set({ showExport: false }),
  setWells: (wells) => set({ wells }),
  setSelectedWell: (selectedWell) => set({ selectedWell }),
  clearResults: () =>
    set({
      verdicts: [],
      replicates: [],
      summary: null,
      wells: [],
      selectedWell: null,
      searchQuery: "",
      runHealth: null,
    }),
  resetAnalysis: () =>
    set({
      verdicts: [],
      replicates: [],
      summary: null,
      plateFilter: "ALL",
      searchQuery: "",
      sorting: [],
      showExport: false,
      wells: [],
      selectedWell: null,
      runHealth: null,
    }),
  loadPlateData: async () => {
    try {
      const result = await sendRequest<PlateDataResult>("get_plate_data", {});
      const firstWell = result.wells.find((well) => well.selected) ?? result.wells[0] ?? null;
      set({ wells: result.wells, selectedWell: firstWell });
    } catch (error) {
      // -32002: analyze not yet run, or other sidecar errors. Clear stale data.
      console.warn("[analysisSlice] loadPlateData failed:", error);
      set({ wells: [], selectedWell: null });
    }
  },
  loadRunHealth: async () => {
    try {
      const result = await sendRequest<RunHealthData>("get_run_health", {});
      set({ runHealth: result });
    } catch (error) {
      console.warn("[analysisSlice] loadRunHealth failed:", error);
      set({ runHealth: null });
    }
  },
  loadSampleData: async () => {
    set({ analyzeMessage: "Loading sample data..." });

    let refPath: string;
    let expectedPath: string;
    let barcodesPath: string;
    let sampleMapPath: string;
    let activityCsvPath: string;
    try {
      [refPath, expectedPath, barcodesPath, sampleMapPath, , activityCsvPath] =
        await Promise.all([
          resolveResource("samples/mame/reference.fasta"),
          resolveResource("samples/mame/03_mame_expected_mutations.xlsx"),
          resolveResource("samples/mame/04_mame_custom_barcodes.xlsx"),
          resolveResource("samples/mame/05_mame_sample_map.xlsx"),
          resolveResource("samples/mame/06_mame_plate_layout.xlsx"),
          resolveResource("samples/mame/07_mame_activity_long.csv"),
        ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ analyzeMessage: `Sample load failed: ${msg}` });
      return;
    }

    // Populate input store via cross-slice setters
    const state = get();
    state.setReferencePath(refPath);
    state.setExpectedPath(expectedPath);
    state.setSampleMapPath(sampleMapPath);
    state.setParams({ rawRunParams: { customBarcodesPath: barcodesPath } });

    // Activity pipeline: set plate meta + upload measurements.
    // Partial-success allowed per Wave B1 spec: RPC failure must not block the
    // mock results screen — user is notified via analyzeMessage.
    const roundId = "sample-round-1";
    let activityErr: unknown = null;
    try {
      await sendRequest("activity.set_plate_meta", {
        round_id: roundId,
        plate_meta: {
          plates: [{ plate_id: "plate01", wt_wells: ["A1", "A2", "A3"] }],
        },
      });
      await sendRequest("activity.upload", {
        round_id: roundId,
        file_path: activityCsvPath,
        format: "csv",
      });
    } catch (rpcErr) {
      activityErr = rpcErr;
      console.warn("[analysisSlice] activity RPC failed, falling back to mock:", rpcErr);
    }

    const wells = sampleWells();
    set({
      verdicts: sampleVerdicts(),
      replicates: sampleReplicates(),
      summary: sampleSummary(),
      wells,
      selectedWell: wells.find((w) => w.selected) ?? wells[0] ?? null,
      analyzeMessage:
        activityErr === null
          ? "Sample data loaded (22 wells, plate01)"
          : `Sample data loaded (results only; activity RPC unavailable: ${
              activityErr instanceof Error ? activityErr.message : String(activityErr)
            })`,
    });
  },
});
