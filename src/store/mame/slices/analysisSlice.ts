import { functionalUpdate } from "@tanstack/react-table";
import { resolveResource } from "@tauri-apps/api/path";
import { readTextFile } from "@tauri-apps/plugin-fs";
import type { StateCreator } from "zustand";
import { sendRequest } from "@/lib/ipc-mame";
import {
  sampleReplicates,
  sampleSummary,
  sampleVerdicts,
  sampleWells,
} from "@/lib/mame/sampleData";
import { seedBuildEvolveproForm } from "@/lib/mame/buildEvolveproFormStorage";
import { useRoundStore } from "@/store/round/roundSlice";
import type { ActivityRecord, PlateMeta } from "@/types/mame/activity";
import type {
  AnalyzeSummary,
  PlateDataResult,
  ReplicateResult,
  RunHealthData,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";
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
  mameSamplePrefill: null,
  consumeMameSamplePrefill: () => set({ mameSamplePrefill: null }),
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

    // Resolve each resource independently so a single missing bundle entry
    // does not abort the whole flow. Critical files (reference.fasta,
    // activity csv) abort with a specific message naming the file; the
    // rest degrade gracefully with a warning listing the failures.
    const relPaths = [
      "samples/mame/reference.fasta",
      "samples/mame/03_mame_expected_mutations.xlsx",
      "samples/mame/04_mame_custom_barcodes.xlsx",
      "samples/mame/05_mame_sample_map.xlsx",
      "samples/mame/06_mame_plate_layout.xlsx",
      "samples/mame/07_mame_activity_long.csv",
      "samples/mame/02_mame_barcode_seeds.xlsx",
      "samples/mame/egfp_with_flanks.fa",
      "samples/mame/08_mame_evolvepro_raw.xlsx",
      "samples/mame/09_mame_agilent_rep_batch.xlsx",
      "samples/mame/10_mame_gc_prenormalised.xlsx",
      "samples/mame/sample_analysis_result.json",
    ];
    const settled = await Promise.allSettled(relPaths.map((p) => resolveResource(p)));
    const resolved: (string | null)[] = settled.map((r, i) => {
      if (r.status === "fulfilled") return r.value;
      console.warn(`[analysisSlice] resolveResource failed for ${relPaths[i]}:`, r.reason);
      return null;
    });

    // Surface the actual rejection reason (not a hardcoded assumption) for the
    // critical-file abort messages below.
    const reasonAt = (i: number): string => {
      const r = settled[i];
      if (r.status === "rejected") {
        return r.reason instanceof Error ? r.reason.message : String(r.reason);
      }
      return "resource missing";
    };
    const [
      refPath,
      expectedPath,
      barcodesPath,
      sampleMapPath,
      layoutXlsxPath,
      activityCsvPath,
      barcodeSeedsPath,
      designFastaPath,
      prevEvolveproXlsxPath,
      repBatchXlsxPath,
      gcDataXlsxPath,
      analysisResultPath,
    ] = resolved;

    // Critical inputs: reference.fasta and activity CSV. Abort with a
    // specific error naming the failing file (explicit user-facing message).
    if (!refPath) {
      set({
        analyzeMessage: `Sample load failed: samples/mame/reference.fasta (${reasonAt(0)})`,
      });
      return;
    }
    if (!activityCsvPath) {
      set({
        analyzeMessage: `Sample load failed: samples/mame/07_mame_activity_long.csv (${reasonAt(5)})`,
      });
      return;
    }

    // Non-critical: collect failed file names for surfacing to the user.
    const optionalFailures: string[] = [];
    if (!expectedPath) optionalFailures.push("03_mame_expected_mutations.xlsx");
    if (!barcodesPath) optionalFailures.push("04_mame_custom_barcodes.xlsx");
    if (!sampleMapPath) optionalFailures.push("05_mame_sample_map.xlsx");
    if (!barcodeSeedsPath) optionalFailures.push("02_mame_barcode_seeds.xlsx");
    if (!designFastaPath) optionalFailures.push("egfp_with_flanks.fa");

    // Populate input store via cross-slice setters (skip ones that failed).
    const state = get();
    state.setReferencePath(refPath);
    if (expectedPath) state.setExpectedPath(expectedPath);
    if (sampleMapPath) state.setSampleMapPath(sampleMapPath);
    if (barcodesPath)
      state.setParams({ rawRunParams: { customBarcodesPath: barcodesPath } });

    // Publish Phase 1 setup prefill for BarcodeSetupPanel (fasta + seeds).
    // The panel's existing fastaPath useEffect autoDetects geneStart/geneEnd
    // via autoDetectCdsCandidates, so we only need to seed these two paths.
    //
    // IMPORTANT: Step 1.2 (barcode-package design) needs a CDS that has
    // flanking sequence on BOTH sides of the gene (>= flank_max, default
    // 400 nt) so primer binding sites can be placed outside the gene. The
    // analyze reference (reference.fasta) is the amplicon itself with zero
    // flank, so it fails primer design ("sequence is too short upstream of
    // the gene"). Prefill the dedicated flank-bearing demo FASTA instead,
    // falling back to refPath only if the flanked file failed to resolve.
    set({
      mameSamplePrefill: {
        fastaPath: designFastaPath ?? refPath,
        barcodeSeedsPath: barcodeSeedsPath ?? "",
      },
    });

    // Activity pipeline: create round + set plate meta (WT wells) + upload measurements.
    // WT wells A1/A2/A3 derived from 05_mame_sample_map.xlsx (rows 2-4 → WT_r1/r2/r3).
    // Round entity is required so WtWellGrid / ActivityPanel can surface the
    // pre-annotated WT wells without forcing the user to redo the click-grid.
    // Partial-success allowed per Wave B1 spec: RPC failure must not block the
    // mock results screen — user is notified via analyzeMessage.
    const samplePlateMeta: PlateMeta = {
      plates: [
        { plate_id: "plate01", wt_wells: ["A1", "A2", "A3"], control_wells: [] },
      ],
    };
    const roundId = useRoundStore.getState().addRound({ plate_meta: samplePlateMeta });
    let activityErr: unknown = null;
    try {
      await sendRequest("activity.set_plate_meta", {
        round_id: roundId,
        plate_meta: samplePlateMeta,
      });
      const uploadResult = await sendRequest<{
        records: ActivityRecord[];
        plate_meta: PlateMeta;
      }>("activity.upload", {
        round_id: roundId,
        file_path: activityCsvPath,
        format: "csv",
      });
      // Hydrate round.activity so WtWellGrid + ActivityPanel reflect the
      // uploaded records and WT-well annotation without re-running upload.
      useRoundStore.getState().updateRoundField(roundId, "activity", {
        records: uploadResult?.records ?? [],
        plate_meta: uploadResult?.plate_meta ?? samplePlateMeta,
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
        (activityErr === null
          ? "Sample data loaded (22 wells, plate01)"
          : `Sample data loaded (results only; activity RPC unavailable: ${
              activityErr instanceof Error ? activityErr.message : String(activityErr)
            })`) +
        (optionalFailures.length > 0
          ? ` (missing optional files: ${optionalFailures.join(", ")})`
          : ""),
    });

    // Task B: Load fixture analysis result to populate graphs (verdicts/wells/runHealth/summary).
    // Append after mock results so fixture overrides them on success; mock remains as graceful fallback.
    if (analysisResultPath) {
      try {
        const fixtureText = await readTextFile(analysisResultPath);
        const fixtureData = JSON.parse(fixtureText) as Pick<
          AppState,
          "verdicts" | "replicates" | "summary" | "wells" | "runHealth"
        >;
        const fixtureWells: WellEntry[] = Array.isArray(fixtureData.wells)
          ? (fixtureData.wells as WellEntry[])
          : [];
        set({
          verdicts: Array.isArray(fixtureData.verdicts)
            ? (fixtureData.verdicts as VerdictRecord[])
            : sampleVerdicts(),
          replicates: Array.isArray(fixtureData.replicates)
            ? (fixtureData.replicates as ReplicateResult[])
            : sampleReplicates(),
          summary: (fixtureData.summary as AnalyzeSummary | null) ?? sampleSummary(),
          wells: fixtureWells,
          selectedWell:
            fixtureWells.find((w) => w.selected) ?? fixtureWells[0] ?? null,
          runHealth: (fixtureData.runHealth as RunHealthData | null) ?? null,
        });
      } catch (fixtureErr) {
        console.warn(
          "[analysisSlice] sample_analysis_result.json load failed, using mock results:",
          fixtureErr,
        );
      }
    }

    // Task C: Seed BuildEvolveproInputPanel form fields via localStorage.
    // Only fills empty fields; existing user selections are preserved.
    seedBuildEvolveproForm({
      layoutXlsx: layoutXlsxPath ?? undefined,
      gcDataXlsx: gcDataXlsxPath ?? undefined,
      repBatchXlsx: repBatchXlsxPath ?? undefined,
      prevEvolveproXlsx: prevEvolveproXlsxPath ?? undefined,
    });
  },
});
