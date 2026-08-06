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
  PlateDataResult,
  RunHealthData,
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
  analyzeYield: null,
  layoutProvenance: null,
  mappingIntegrity: null,
  compareParams: null,
  offLayoutRecords: null,
  contamination: null,
  restoredResultProvenance: null,
  // FINAL (the per-mutant selected replicate) is the default view: it is the
  // answer sheet a run is read for. VerdictTable degrades it to ALL while no
  // replicate has been selected, so the default never shows an empty table.
  plateFilter: "FINAL",
  searchQuery: "",
  sorting: [],
  showExport: false,
  wells: [],
  selectedWell: null,
  runHealth: null,
  buildEvolveproCompletion: null,
  mameSamplePrefill: null,
  consumeMameSamplePrefill: () => set({ mameSamplePrefill: null }),
  setVerdicts: (verdicts) => set({ verdicts }),
  setReplicates: (replicates) => set({ replicates }),
  setSummary: (summary) => set({ summary }),
  setAnalyzeYield: (analyzeYield) => set({ analyzeYield }),
  setLayoutProvenance: (layoutProvenance) => set({ layoutProvenance }),
  setMappingIntegrity: (mappingIntegrity) => set({ mappingIntegrity }),
  setCompareParams: (compareParams) => set({ compareParams }),
  setOffLayoutRecords: (offLayoutRecords) => set({ offLayoutRecords }),
  setContamination: (contamination) => set({ contamination }),
  setRestoredResultProvenance: (restoredResultProvenance) =>
    set({ restoredResultProvenance }),
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
  setBuildEvolveproCompletion: (buildEvolveproCompletion) =>
    set({ buildEvolveproCompletion }),
  // Single definition of "everything the last completed analyze run produced".
  // Both a fresh analysis (resetAnalysis, via resetMameAll) and an input change
  // that invalidates a prior run (inputSlice setters) call this, so a new
  // result field only ever needs to be added here once. `set`'s state type
  // parameter is the full AppState (see mameAppStore.ts's shared-args combine
  // pattern), so this may legally write janusAutosave/janusMappingAutosave too
  // even though they are declared on InputSlice: they describe what the LAST
  // run wrote to disk, which is exactly a run output, not an input field. A
  // stale autosave banner describing a file no longer connected to the picked
  // inputs was the 2026-08-06 incident this consolidation closes.
  clearResults: () =>
    set({
      verdicts: [],
      replicates: [],
      summary: null,
      analyzeYield: null,
      layoutProvenance: null,
      mappingIntegrity: null,
      // Thresholds describe the run that produced the verdicts being cleared;
      // keeping them would let a metric popup state what an input the operator
      // has since changed would have been judged against.
      compareParams: null,
      offLayoutRecords: null,
      // Measured against the wells THESE verdicts were scored on, so it stops
      // meaning anything the moment they go.
      contamination: null,
      // The restored-result notice describes the results being cleared here, so
      // it must not outlive them: a fresh run or an input change makes whatever
      // an older build produced irrelevant.
      restoredResultProvenance: null,
      wells: [],
      selectedWell: null,
      searchQuery: "",
      runHealth: null,
      buildEvolveproCompletion: null,
      janusAutosave: null,
      janusMappingAutosave: null,
      // The replicate axis is a property of the results, not of the form: it
      // says which plate copies the verdicts above were scored on. Once those
      // verdicts are gone it describes nothing, and a stale axis would have
      // ReplicateModeNotice and the concordance flags speak about a run that is
      // no longer on screen. Both drop back to null ("no axis stated"), which
      // is deliberately not `[]` ("pooled, one plate").
      selectedNativeBarcodes: null,
      detectedBarcodeCount: null,
    }),
  resetAnalysis: () => {
    get().clearResults();
    set({
      plateFilter: "FINAL",
      sorting: [],
      showExport: false,
    });
  },
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
      "samples/mame/06_mame_plate_layout.xlsx",
      "samples/mame/07_mame_activity_long.csv",
      "samples/mame/02_mame_barcode_seeds.xlsx",
      "samples/mame/egfp_with_flanks.fa",
      "samples/mame/09_mame_agilent_rep_batch.xlsx",
      "samples/mame/10_mame_gc_prenormalised.xlsx",
      "samples/mame/11_mame_gc_fid_round1_raw.xlsx",
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
    // Index-sensitive: `reasonAt` below indexes into `settled`, which is
    // `relPaths` in order, so a removed entry renumbers every later one.
    const [
      refPath,
      expectedPath,
      barcodesPath,
      layoutXlsxPath,
      activityCsvPath,
      barcodeSeedsPath,
      designFastaPath,
      variantLabelsReportPath,
      gcDataXlsxPath,
      round1ReportXlsxPath,
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
        analyzeMessage: `Sample load failed: samples/mame/07_mame_activity_long.csv (${reasonAt(4)})`,
      });
      return;
    }

    // Non-critical: collect failed file names for surfacing to the user.
    const optionalFailures: string[] = [];
    if (!expectedPath) optionalFailures.push("03_mame_expected_mutations.xlsx");
    if (!barcodesPath) optionalFailures.push("04_mame_custom_barcodes.xlsx");
    if (!barcodeSeedsPath) optionalFailures.push("02_mame_barcode_seeds.xlsx");
    if (!designFastaPath) optionalFailures.push("egfp_with_flanks.fa");
    if (!variantLabelsReportPath)
      optionalFailures.push("09_mame_agilent_rep_batch.xlsx");
    if (!gcDataXlsxPath) optionalFailures.push("10_mame_gc_prenormalised.xlsx");
    if (!round1ReportXlsxPath)
      optionalFailures.push("11_mame_gc_fid_round1_raw.xlsx");

    // Populate input store via cross-slice setters (skip ones that failed).
    //
    // The analyze reference is the flank-bearing construct, not the bare CDS.
    // `04_mame_custom_barcodes.xlsx` is regenerated by
    // `python-core/scripts/regen_mame_sample_barcodes.py` from
    // `egfp_with_flanks.fa`, so its flanking primers bind in the synthetic
    // flanks and exist nowhere inside `reference.fasta` (the bare 720 bp EGFP
    // CDS). Pairing the demo's barcodes with the bare CDS made
    // `resolve_amplicon_reference` report NOT_FOUND every single time, so the
    // one path the demo could never show was the successful one. Against the
    // construct the same primers were designed in, the span resolves (51-1275,
    // 1225 bp), which is also exactly the amplicon step 1.2 would hand back.
    // `reference.fasta` stays bundled and stays the fallback: if the flanked
    // file fails to resolve, the demo still runs, just without extraction.
    const state = get();
    state.setReferencePath(designFastaPath ?? refPath);
    if (expectedPath) state.setExpectedPath(expectedPath);
    if (barcodesPath)
      state.setParams({ rawRunParams: { customBarcodesPath: barcodesPath } });

    // Publish Phase 1 setup prefill for BarcodeSetupPanel (fasta + seeds).
    // The panel's existing fastaPath useEffect autoDetects geneStart/geneEnd
    // via autoDetectCdsCandidates, so we only need to seed these two paths.
    //
    // IMPORTANT: Step 1.2 (barcode-package design) needs a CDS that has
    // flanking sequence on BOTH sides of the gene (>= flank_max, default
    // 400 nt) so primer binding sites can be placed outside the gene. That is
    // the same file the analyze reference above now takes, and deliberately
    // so: one construct describes the whole demo, so what step 1.2 designs
    // primers in is what step 2 extracts the amplicon from. The fallback
    // differs in consequence, though. Falling back to `reference.fasta` here
    // fails primer design outright ("sequence is too short upstream of the
    // gene"), whereas analyze merely skips extraction.
    set({
      mameSamplePrefill: {
        fastaPath: designFastaPath ?? refPath,
        barcodeSeedsPath: barcodeSeedsPath ?? "",
      },
    });

    // Activity pipeline: create round + set plate meta (WT wells) + upload measurements.
    // WT wells A1/A2/A3 derived from 06_mame_plate_layout.xlsx (rows 2-4 → WT_r1/r2/r3).
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
      // Sample data carries no demux yield or mapping provenance; drop any
      // left over from a real run.
      analyzeYield: null,
      layoutProvenance: null,
      mappingIntegrity: null,
      offLayoutRecords: null,
      // Sample data is a consensus-dir fixture and never demuxed, so there is
      // no matrix behind it. null, not an empty report.
      contamination: null,
      // The replicate axis goes with them. The sample verdicts carry
      // `barcode1`, `barcode2`, ... as their native_barcode (lib/mame/
      // sampleData.ts), so a `sort_barcodeNN` selection left over from a real
      // run marks EVERY sample well `missing_replicate` and has
      // ReplicateModeNotice compare that run's barcode count against this
      // fixture. null is "no axis stated", deliberately not `[]` ("pooled").
      selectedNativeBarcodes: null,
      detectedBarcodeCount: null,
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

    // Task B: Load fixture analysis result to populate the run-health graphs.
    // Only runHealth is missing — verdicts/wells/summary are already set from
    // the mock helpers above. Setting runHealth makes the Per-plate verdict
    // breakdown render instead of showing "Setup incomplete".
    if (analysisResultPath) {
      try {
        const fixtureText = await readTextFile(analysisResultPath);
        const fixtureData = JSON.parse(fixtureText) as { runHealth?: RunHealthData };
        if (fixtureData.runHealth) {
          set({ runHealth: fixtureData.runHealth });
        }
      } catch (fixtureErr) {
        console.warn(
          "[analysisSlice] sample_analysis_result.json load failed:",
          fixtureErr,
        );
      }
    }

    // Seed the supported Step 3 inputs for this project only.
    seedBuildEvolveproForm(
      {
        activityPath: activityCsvPath,
        layoutXlsx: layoutXlsxPath ?? undefined,
        gcDataXlsx: gcDataXlsxPath ?? undefined,
        round1ReportXlsx: round1ReportXlsxPath ?? undefined,
        remeasureReportXlsx: variantLabelsReportPath ?? undefined,
      },
      get().projectPath,
    );
  },
});
