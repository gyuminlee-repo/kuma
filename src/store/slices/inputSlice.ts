import type { StateCreator } from "zustand";
import { resolveResource } from "@tauri-apps/api/path";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type { Round } from "../../types/round";
import {
  buildEvolveproLoadParams,
  buildEvolveproLoadStateUpdate,
  collectAnchorVariants,
  resolveSelectionDomains,
} from "./inputSlice.helpers";
import { useMameAppStore } from "../mame/mameAppStore";
import { useRoundStore } from "../round/roundSlice";

import type { InputSlice, EvolveproMode } from "../slice-interfaces";
export type { InputSlice };

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => {
  let csvLoadGeneration = 0;

  return ({
  mutationInputMode: "evolvepro",
  mutationText: "",
  parsedMutations: [],
  parseErrors: [],
  evolveproCsvPath: "",
  evolveproTotalCount: 0,
  evolveproFilteredCount: null,
  evolveproParetoExchanges: null,
  evolveproStepStats: null,
  yPredMap: {},
  evolveproMode: "topN" as EvolveproMode,
  evolveproVariantColumn: null,
  evolveproScoreColumn: null,
  evolveproScoreOrder: "desc" as const,
  evolveproSheetName: null,
  evolveproPreview: null,
  evolveproUsedVariantColumn: null,
  evolveproUsedScoreColumn: null,
  evolveproRankedCandidates: [],
  evolveproSelectedVariants: [],
  evolveproExtraExposed: 10,

  setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
  setMutationText: (text) => set({ mutationText: text }),

  loadEvolveproCsv: async (filepath: string, topNOverride?: number) => {
    const gen = ++csvLoadGeneration;
    try {
      const {
        evolveproMode,
        evolveproVariantColumn,
        evolveproScoreColumn,
        evolveproScoreOrder,
        evolveproSheetName,
        positionDiversityEnabled,
        maxPerPosition,
        domainDiversityEnabled,
        refDomains,
        disabledDomains,
        domainStrategy,
        domainOverlapPolicy,
        linkerHandling,
        domainQuotaMin,
        paretoDiversityEnabled,
        entropyWeightEnabled,
        entropyWeight,
        paretoPoolMultiplier,
        distanceMode,
        evolveproRound,
        roundSize,
        maxPrimers,
        structuralDiversityEnabled,
        structuralKappa,
      } = get();
      const effectiveTopN = topNOverride ?? maxPrimers;
      const selectionDomains = resolveSelectionDomains(refDomains);
      const activeDomains = selectionDomains.filter((d) => !disabledDomains.includes(`${d.name}-${d.start}`));
      const excludedDomains = selectionDomains.filter((d) => disabledDomains.includes(`${d.name}-${d.start}`));
      const modeLabel = "EVOLVEpro";

      // v0.3 §4: pass protein ref_seq so sidecar can convert EVOLVEpro
      // short-form variants (89W) back to internal notation (F89W).
      // Pulled from the selected gene's translation when available.
      const seqInfo = get().seqInfo;
      const selectedGeneKey = get().selectedGene;
      const refSeq = (() => {
        if (!seqInfo) return "";
        const gene = seqInfo.genes.find((g) => String(g.cds_start) === selectedGeneKey)
          ?? seqInfo.genes[0];
        return gene?.translation ?? "";
      })();
      set({
        statusMessage: `Loading ${modeLabel} file...`,
        evolveproCsvPath: filepath,
      });

      // §3 Input Guards: column header validation now delegated entirely to
      // the sidecar's auto-detect (VARIANT_COLUMNS/SCORE_COLUMNS alias) -
      // custom column names are a supported input, not a format error.

      const usePipeline = evolveproMode !== "topN";
      // Structural-diversity revealed-anchor maximin: spread new picks away
      // from variants already committed across prior rounds. Only computed
      // when structural diversity is on (the sole consumer); empty otherwise.
      const anchorVariants =
        usePipeline && structuralDiversityEnabled
          ? collectAnchorVariants(useRoundStore.getState().rounds)
          : [];
        const params = buildEvolveproLoadParams({
          filepath,
          topN: effectiveTopN,
          usePipeline,
          evolveproVariantColumn,
          evolveproScoreColumn,
          evolveproScoreOrder,
          evolveproSheetName,
        positionDiversityEnabled,
        maxPerPosition,
        activeDomains,
        excludedDomains,
        domainDiversityEnabled,
        domainStrategy,
        domainOverlapPolicy,
        linkerHandling,
        domainQuotaMin,
        paretoDiversityEnabled,
        entropyWeightEnabled,
          entropyWeight,
          paretoPoolMultiplier,
          distanceMode,
          // A user-loaded structure file sets structureAccession (file:...) but
          // not uniprotAccession, so the file key must win. Same order as
          // Selection3DPanel. Sending uniprotAccession alone here silently
          // dropped file coordinates and left 3D selection on 1-D distance.
          structureAccession: get().structureAccession || get().uniprotAccession,
          evolveproRound,
          roundSize,
          refSeq,
          structuralDiversityEnabled,
          structuralKappa,
          anchorVariants,
        });
      const result = await sendRequest("load_evolvepro_csv", params);
      if (gen !== csvLoadGeneration) return;
      const update = buildEvolveproLoadStateUpdate({
        result,
        currentMode: get().mutationInputMode,
        maxPerPosition,
        threeDConsumerOn: get().paretoDiversityEnabled || get().structuralDiversityEnabled,
        structureLoaded: get().structureLoaded,
      });
      if (result.total_count > 0 && maxPrimers > result.total_count) {
        get().setMaxPrimers(result.total_count);
      }
      set({
        mutationText: update.mutationText,
        mutationInputMode: "evolvepro",
        yPredMap: update.yPredMap,
        domainStats: update.domainStats,
        poolVariants: update.poolVariants,
        evolveproTotalCount: update.evolveproTotalCount,
        evolveproFilteredCount: update.evolveproFilteredCount,
        evolveproParetoExchanges: update.evolveproParetoExchanges,
        evolveproStepStats: update.evolveproStepStats,
        structure3dState: update.structure3dState,
        statusMessage: update.statusMessage,
        evolveproRankedCandidates: result.ranked_candidates ?? [],
        // Initialize selection directly from result.variants (pipeline source-of-truth).
        // ranked_candidates is guaranteed to contain all selected variants (backend invariant:
        // selected ⊆ ranked_candidates), but we seed from result.variants for authority clarity.
        evolveproSelectedVariants: result.variants ?? [],
        evolveproUsedVariantColumn: result.used_variant_column ?? null,
        evolveproUsedScoreColumn: result.used_score_column ?? null,
      });

      // Dual-write to MAME shared store so other panels can auto-fill.
      try {
        useMameAppStore.getState().setSharedEvolveproCsvPath(filepath);
      } catch {
        // Defensive: never let the cross-store hand-off break CSV load.
      }
    } catch (err) {
      if (gen === csvLoadGeneration) {
        const modeLabel = "EVOLVEpro";
        set({
          mutationText: "",
          evolveproTotalCount: 0,
          evolveproFilteredCount: null,
          evolveproParetoExchanges: null,
          evolveproStepStats: null,
          yPredMap: {},
          domainStats: {},
          poolVariants: [],
          evolveproRankedCandidates: [],
          evolveproSelectedVariants: [],
          statusMessage: `${modeLabel} file load failed: ${formatError(err)}`,
        });
      }
      throw err;
    }
  },

  setEvolveproMode: (mode: EvolveproMode) => {
    set({ evolveproMode: mode });
    // Switching between topN / pipeline changes which params are sent; reload
    // the already-loaded file so the backend re-applies the correct pipeline.
    const path = get().evolveproCsvPath;
    if (path) {
      void get().loadEvolveproCsv(path);
    }
  },
  setEvolveproVariantColumn: (col) => set({ evolveproVariantColumn: col, evolveproUsedVariantColumn: null }),
  setEvolveproScoreColumn: (col) => set({ evolveproScoreColumn: col, evolveproUsedScoreColumn: null }),
  setEvolveproScoreOrder: (order) => set({ evolveproScoreOrder: order }),
  setEvolveproSheetName: (name) => set({ evolveproSheetName: name }),
  setEvolveproPreview: (preview) => set({ evolveproPreview: preview }),

  setEvolveproVariantSelected: (variant, selected) => {
    const current = get().evolveproSelectedVariants;
    if (selected) {
      if (!current.includes(variant)) {
        set({ evolveproSelectedVariants: [...current, variant] });
      }
    } else {
      set({ evolveproSelectedVariants: current.filter((v) => v !== variant) });
    }
  },

  setEvolveproExtraExposed: (count) => set({ evolveproExtraExposed: Math.max(0, count) }),

  parseMutations: async () => {
    const { mutationText } = get();
    try {
      const result = await sendRequest(
        "parse_mutations_text",
        { text: mutationText },
      );
      set({ parsedMutations: result.parsed, parseErrors: result.errors });
    } catch (err) {
      set({ statusMessage: `Mutation parse failed: ${formatError(err)}` });
    }
  },

  loadSampleData: async () => {
    // Auto-populate every required field so the user can press Next at each
    // wizard step without manual setup. Mode-aware: evolvepro mode loads the
    // EGFP-compatible CSV (since v0.9.9.X), text mode injects the 120 demo
    // mutations verified against the bundled EGFP translation.
    try {
      set({ statusMessage: "Loading sample data..." });
      const gbPath = await resolveResource("samples/sample_plasmid.gb");
      await get().loadSequence(gbPath);
      if (!get().seqInfo) {
        // loadSequence swallowed an error and left statusMessage with the cause; preserve it.
        return;
      }
      const csvPath = await resolveResource("samples/sample_evolvepro.csv");
      await get().loadEvolveproCsv(csvPath);
      set({ statusMessage: "Sample data loaded (EGFP + EVOLVEpro CSV)." });
    } catch (err) {
      set({ statusMessage: `Sample load failed: ${formatError(err)}` });
    }
  },

  loadRoundActivity: (prevRound: Round) => {
    const warnings: string[] = [];

    // Step 1: filter merged_table — ngs_success && mutation && mutation !== "WT" && log2_fc !== null
    const filtered = prevRound.merged_table.filter(
      (r) =>
        r.ngs_success &&
        r.mutation !== null &&
        r.mutation !== undefined &&
        r.mutation !== "WT" &&
        r.log2_fc !== null &&
        r.log2_fc !== undefined,
    );

    // Step 7: 0 rows → ok=false, no state change
    if (filtered.length === 0) {
      warnings.push("0 rows after filter (ngs_success && non-WT && log2_fc not null)");
      return { ok: false, warnings };
    }

    // Step 2: build yPredMap (variant → log2_fc)
    const yPredMap: Record<string, number> = {};
    const variants: string[] = [];
    for (const r of filtered) {
      const variant = r.mutation as string;
      yPredMap[variant] = r.log2_fc as number;
      if (!variants.includes(variant)) {
        variants.push(variant);
      }
    }

    // Steps 3–6: apply state updates
    // Note: mutationText = variants.join("\n") for design pipeline compatibility.
    // Spec §4.5 step 5 literal (mutationText="") would break KURO design which
    // reads mutationText as primary variant input. Deviation documented in PR.
    // Build ranked_candidates from round data (no CSV, so use log2_fc as y_pred proxy).
    const roundRankedCandidates = variants.map((v) => ({
      variant: v,
      y_pred: yPredMap[v] ?? 0,
      aa_position: null as number | null,
    })).sort((a, b) => b.y_pred - a.y_pred);
    set({
      // Step 3: force evolvepro mode
      mutationInputMode: "evolvepro",
      // Step 4/5: hydrate evolvepro state (evolvepro rows → mutationText + yPredMap)
      mutationText: variants.join("\n"),
      yPredMap,
      evolveproTotalCount: filtered.length,
      evolveproCsvPath: "",  // memory hydrate — no CSV file path
      // Step 6: clear stale diversity cache
      evolveproFilteredCount: null,
      evolveproParetoExchanges: null,
      evolveproStepStats: null,
      domainStats: {},
      poolVariants: [],
      evolveproRankedCandidates: roundRankedCandidates,
      evolveproSelectedVariants: [...variants],
      statusMessage: `Round ${prevRound.n} activity loaded: ${filtered.length} variants (EVOLVEpro mode)`,
    });

    return { ok: true, warnings };
  },
});
};
