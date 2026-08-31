import { functionalUpdate } from "@tanstack/react-table";
import { resolveResource } from "@tauri-apps/api/path";
import { exists, readTextFile } from "@tauri-apps/plugin-fs";
import i18next from "i18next";
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

/** `src-tauri/samples/mame/sample_analysis_result.json`.
 *
 * Written by `python-core/scripts/generate_mame_step4_samples.py`, which
 * serialises a real pipeline run through the same handlers the sidecar answers
 * a live Analyze with. Every field is therefore the shape a run produces, and
 * each is optional here because a bundle that lost the file should degrade to
 * the fallback rather than throw on a missing key.
 */
type SampleAnalysisFixture = {
  verdicts?: VerdictRecord[];
  replicates?: ReplicateResult[];
  summary?: AnalyzeSummary;
  wells?: WellEntry[];
  runHealth?: RunHealthData;
};

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
  staleUnits: null,
  compareParams: null,
  offLayoutRecords: null,
  runQuality: null,
  contamination: null,
  referenceResolution: null,
  restoredResultProvenance: null,
  demuxResume: null,
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
  sampleDataLoaded: false,
  buildEvolveproSeedEpoch: 0,
  bumpBuildEvolveproSeedEpoch: () =>
    set((s) => ({ buildEvolveproSeedEpoch: s.buildEvolveproSeedEpoch + 1 })),
  setVerdicts: (verdicts) => set({ verdicts }),
  setReplicates: (replicates) => set({ replicates }),
  setSummary: (summary) => set({ summary }),
  setAnalyzeYield: (analyzeYield) => set({ analyzeYield }),
  setLayoutProvenance: (layoutProvenance) => set({ layoutProvenance }),
  setMappingIntegrity: (mappingIntegrity) => set({ mappingIntegrity }),
  setStaleUnits: (staleUnits) => set({ staleUnits }),
  setCompareParams: (compareParams) => set({ compareParams }),
  setOffLayoutRecords: (offLayoutRecords) => set({ offLayoutRecords }),
  setRunQuality: (runQuality) => set({ runQuality }),
  setContamination: (contamination) => set({ contamination }),
  setReferenceResolution: (referenceResolution) => set({ referenceResolution }),
  setRestoredResultProvenance: (restoredResultProvenance) =>
    set({ restoredResultProvenance }),
  setDemuxResume: (demuxResume) => set({ demuxResume }),
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
      staleUnits: null,
      // Thresholds describe the run that produced the verdicts being cleared;
      // keeping them would let a metric popup state what an input the operator
      // has since changed would have been judged against.
      compareParams: null,
      offLayoutRecords: null,
      runQuality: null,
      // Measured against the wells THESE verdicts were scored on, so it stops
      // meaning anything the moment they go.
      contamination: null,
      // Which reference the run being cleared actually read. It describes that
      // run, not the file currently in the form, so a notice about a slice
      // must not survive into the next set of inputs.
      referenceResolution: null,
      // The restored-result notice describes the results being cleared here, so
      // it must not outlive them: a fresh run or an input change makes whatever
      // an older build produced irrelevant.
      restoredResultProvenance: null,
      demuxResume: null,
      wells: [],
      selectedWell: null,
      searchQuery: "",
      runHealth: null,
      buildEvolveproCompletion: null,
      // Nothing here touches what step 4.2 answered. That answer is computed
      // from per-round xlsx files the operator picks, not from the analyze
      // inputs being invalidated here, and it lives on the round rather than in
      // this store. It is not deleted anywhere: whether it still describes its
      // files is decided by comparing them (lib/round/roundArtifacts.ts), so an
      // answer that no longer holds reads as history instead of disappearing.
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
      // Describes the results being cleared, same as the fields above: a real
      // input change or a project switch means whatever is on screen next did
      // not come from the sample bundle, so the step-2 run-folder notice must
      // not carry over.
      sampleDataLoaded: false,
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
      // Appended rather than inserted: `reasonAt` indexes into this list, so a
      // new entry in the middle renumbers every message below it.
      "samples/mame/13_mame_verdict.xlsx",
      "samples/mame/14_mame_activity_long_raw.csv",
      "samples/mame/12_mame_agilent_numeric_index.xlsx",
      "samples/mame/16_mame_agilent_numeric_confirmation.xlsx",
    ];
    // Bundled but deliberately not seeded here (not a gap, no free form
    // field to put them in):
    // - 07_mame_activity_long.xlsx: same activityPath slot as
    //   14_mame_activity_long_raw.csv, which is seeded; this is just the
    //   xlsx-format twin of that one input.
    // - 15_mame_activity_variant.csv: same activityPath slot again, the
    //   variant-labelled twin.
    // - 08_mame_evolvepro_raw.xlsx: no current form field takes it.
    //   round1EvolveproXlsx/repBatchXlsx only exist in
    //   buildEvolveproFormStorage.ts's LEGACY_PATH_KEYS migration list, not
    //   in BuildEvolveproFormState.
    // `resolveResource` only concatenates a path; it never touches disk (see
    // `node_modules/@tauri-apps/api/path.js`, `plugin:path|resolve_directory`).
    // A bundle entry that was deleted still "resolves" successfully, which is
    // why every one of these must also be checked with `exists()` before it
    // is treated as present. Without this, a missing file reads as a
    // successful load here and only fails much later inside the sidecar
    // (`activity_path not found`, `Input xlsx not found`), by which point the
    // path has already been seeded into the step 4 form.
    const settled = await Promise.allSettled(
      relPaths.map(async (p) => {
        const resolvedPath = await resolveResource(p);
        if (!(await exists(resolvedPath))) {
          throw new Error(`resource missing: ${resolvedPath}`);
        }
        return resolvedPath;
      }),
    );
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
      verdictXlsxPath,
      activityRawCsvPath,
      numericReportXlsxPath,
      remeasureNumericXlsxPath,
    ] = resolved;

    // Critical inputs: reference.fasta and activity CSV. Abort with a
    // specific error naming the failing file (explicit user-facing message).
    if (!refPath) {
      set({
        analyzeMessage: i18next.t("mame.sampleData.loadFailed", {
          file: "samples/mame/reference.fasta",
          reason: reasonAt(0),
        }),
      });
      return;
    }
    if (!activityCsvPath) {
      set({
        analyzeMessage: i18next.t("mame.sampleData.loadFailed", {
          file: "samples/mame/07_mame_activity_long.csv",
          reason: reasonAt(4),
        }),
      });
      return;
    }

    // Non-critical: collect failed file names for surfacing to the user.
    const optionalFailures: string[] = [];
    if (!expectedPath) optionalFailures.push("03_mame_expected_mutations.xlsx");
    if (!barcodesPath) optionalFailures.push("04_mame_custom_barcodes.xlsx");
    if (!layoutXlsxPath) optionalFailures.push("06_mame_plate_layout.xlsx");
    if (!barcodeSeedsPath) optionalFailures.push("02_mame_barcode_seeds.xlsx");
    if (!designFastaPath) optionalFailures.push("egfp_with_flanks.fa");
    if (!variantLabelsReportPath)
      optionalFailures.push("09_mame_agilent_rep_batch.xlsx");
    if (!gcDataXlsxPath) optionalFailures.push("10_mame_gc_prenormalised.xlsx");
    if (!round1ReportXlsxPath)
      optionalFailures.push("11_mame_gc_fid_round1_raw.xlsx");
    if (!analysisResultPath) optionalFailures.push("sample_analysis_result.json");
    if (!verdictXlsxPath) optionalFailures.push("13_mame_verdict.xlsx");
    if (!activityRawCsvPath)
      optionalFailures.push("14_mame_activity_long_raw.csv");
    if (!numericReportXlsxPath)
      optionalFailures.push("12_mame_agilent_numeric_index.xlsx");
    if (!remeasureNumericXlsxPath)
      optionalFailures.push("16_mame_agilent_numeric_confirmation.xlsx");

    // The fixture is read before anything is shown, because what it holds
    // decides what gets shown. It is the output of a real pipeline run over the
    // same variant list, plate and reference the rest of the sample set names,
    // so the results screen states the campaign the other files describe. The
    // hand-written mocks below are the fallback for a bundle that lost the
    // file: they are internally consistent but describe a different plate, so
    // reaching for them means the demo no longer agrees with itself.
    let fixture: SampleAnalysisFixture | null = null;
    if (analysisResultPath) {
      try {
        fixture = JSON.parse(
          await readTextFile(analysisResultPath),
        ) as SampleAnalysisFixture;
      } catch (fixtureErr) {
        console.warn(
          "[analysisSlice] sample_analysis_result.json load failed:",
          fixtureErr,
        );
        optionalFailures.push("sample_analysis_result.json");
      }
    }

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
    // The control well is the one `06_mame_plate_layout.xlsx` marks WT, which
    // is where `build_draft_layout` seats the control row of the variant list.
    // Round entity is required so WtWellGrid / ActivityPanel can surface the
    // pre-annotated WT wells without forcing the user to redo the click-grid.
    // Partial-success allowed per Wave B1 spec: RPC failure must not block the
    // mock results screen — user is notified via analyzeMessage.
    const samplePlateMeta: PlateMeta = {
      plates: [
        { plate_id: "plate01", wt_wells: ["H12"], control_wells: [] },
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

    const wells = fixture?.wells ?? sampleWells();
    set({
      verdicts: fixture?.verdicts ?? sampleVerdicts(),
      replicates: fixture?.replicates ?? sampleReplicates(),
      summary: fixture?.summary ?? sampleSummary(),
      // Sample data carries no demux yield or mapping provenance; drop any
      // left over from a real run.
      analyzeYield: null,
      layoutProvenance: null,
      mappingIntegrity: null,
      staleUnits: null,
      offLayoutRecords: null,
      runQuality: null,
      // Sample data is a consensus-dir fixture and never demuxed, so there is
      // no matrix behind it. null, not an empty report.
      contamination: null,
      // Same reason: the fixture resolves no reference, so nothing here was
      // measured. null is "no run reported one", which is what the fixture is;
      // leaving a real run's slice would have the notice describe a reference
      // these sample verdicts were never scored against.
      referenceResolution: null,
      // The replicate axis goes with them. The sample verdicts carry
      // `barcode1`, `barcode2`, ... as their native_barcode (lib/mame/
      // sampleData.ts), so a `sort_barcodeNN` selection left over from a real
      // run marks EVERY sample well `missing_replicate` and has
      // ReplicateModeNotice compare that run's barcode count against this
      // fixture. null is "no axis stated", deliberately not `[]` ("pooled").
      selectedNativeBarcodes: null,
      detectedBarcodeCount: null,
      demuxResume: null,
      // The bundle ships no MinKNOW run folder (kept out for size), so
      // `inputDir` stays empty even though every other field above is filled.
      // Read by InputPanel to explain that empty field instead of leaving it
      // looking abandoned.
      sampleDataLoaded: true,
      wells,
      selectedWell: wells.find((w) => w.selected) ?? wells[0] ?? null,
      // The well count is read off what was loaded rather than stated here. A
      // literal went stale the moment the sample plate changed shape, and it
      // said 22 while the screen showed something else.
      analyzeMessage:
        (activityErr === null
          ? `Sample data loaded (${wells.length} wells, plate01)`
          : `Sample data loaded (results only; activity RPC unavailable: ${
              activityErr instanceof Error ? activityErr.message : String(activityErr)
            })`) +
        (optionalFailures.length > 0
          ? ` ${i18next.t("mame.sampleData.optionalMissing", {
              files: optionalFailures.join(", "),
            })}`
          : ""),
    });

    // Run health comes from the same fixture, which is why the per-plate
    // breakdown renders instead of "Setup incomplete".
    if (fixture?.runHealth) {
      set({ runHealth: fixture.runHealth });
    }

    // Seed the step 4 inputs for this project only.
    //
    // The raw long-format file is the one seeded as the measurement source
    // because the form opens on the raw scale. Seeding the already-relative
    // twin left the demo one dropdown away from a build that divides values by
    // a wild-type mean they were already divided by.
    //
    // `verdictXlsx` is seeded too. It is a required input with no other source
    // in sample data: nothing here runs Analyze, so without it every build
    // stopped at "verdict_xlsx is required" and step 4 could be looked at but
    // not finished.
    // Keyed on `formStoragePath`, not `projectPath`: the latter is null for a
    // scratch session (it gates the result-snapshot file write), but
    // BuildEvolveproInputPanel reads its storage row off
    // `useKumaProject().path` regardless of scratch, and `formStoragePath` is
    // the always-populated mirror of that same path.
    seedBuildEvolveproForm(
      {
        activityPath: activityRawCsvPath ?? activityCsvPath,
        layoutXlsx: layoutXlsxPath ?? undefined,
        gcDataXlsx: gcDataXlsxPath ?? undefined,
        round1ReportXlsx: round1ReportXlsxPath ?? undefined,
        remeasureReportXlsx: variantLabelsReportPath ?? undefined,
        numericReportXlsx: numericReportXlsxPath ?? undefined,
        remeasureNumericXlsx: remeasureNumericXlsxPath ?? undefined,
        verdictXlsx: verdictXlsxPath ?? undefined,
        expectedXlsx: expectedPath ?? undefined,
      },
      get().formStoragePath,
    );
    // A mounted BuildEvolveproInputPanel already read its form from storage
    // (possibly before this seed landed, since seeding only touches
    // localStorage). Bump the epoch so it re-reads now that the sample paths
    // are in.
    get().bumpBuildEvolveproSeedEpoch();
  },
});
