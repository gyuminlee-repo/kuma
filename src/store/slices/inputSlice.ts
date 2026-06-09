import i18next from "i18next";
import type { StateCreator } from "zustand";
import { resolveResource } from "@tauri-apps/api/path";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type { Round } from "../../types/round";
import {
  buildEvolveproLoadParams,
  buildEvolveproLoadStateUpdate,
} from "./inputSlice.helpers";
import {
  validateCsvHeader,
  extractCsvHeader,
  EVOLVEPRO_CSV_SCHEMA,
} from "../../lib/schemaValidator";
import { useMameAppStore } from "../mame/mameAppStore";

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
  othersSourcePath: "",
  othersVariantColumn: null,
  othersScoreColumn: null,
  othersScoreOrder: "desc" as const,
  othersSheetName: null,
  othersPreview: null,
  othersUsedVariantColumn: null,
  othersUsedScoreColumn: null,
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
        othersVariantColumn,
        othersScoreColumn,
        othersScoreOrder,
        othersSheetName,
        positionDiversityEnabled,
        maxPerPosition,
        domainDiversityEnabled,
        domains,
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
      } = get();
      const effectiveTopN = topNOverride ?? maxPrimers;
      const activeDomains = domains.filter((d) => !disabledDomains.includes(`${d.name}-${d.start}`));
      const excludedDomains = domains.filter((d) => disabledDomains.includes(`${d.name}-${d.start}`));
      const isOthersMode = evolveproMode === "others";
      const modeLabel = isOthersMode ? "Others" : "EVOLVEpro";
      const activeVariantColumn = isOthersMode ? othersVariantColumn : evolveproVariantColumn;
      const activeScoreColumn = isOthersMode ? othersScoreColumn : evolveproScoreColumn;
      const activeScoreOrder = isOthersMode ? othersScoreOrder : evolveproScoreOrder;
      const activeSheetName = isOthersMode ? othersSheetName : evolveproSheetName;

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
        ...(isOthersMode ? { othersSourcePath: filepath } : { evolveproCsvPath: filepath }),
      });

      // §3 Input Guards: sidecar 호출 전 헤더 컬럼 검증
      // xlsx/xls 는 바이너리이므로 클라이언트 사전 검증 스킵 (sidecar 에서 검증)
      const ext = filepath.toLowerCase().split(".").pop() ?? "";
      if (!isOthersMode && (ext === "csv" || ext === "tsv")) {
        try {
          const csvText = await readTextFile(filepath);
          const header = extractCsvHeader(csvText, ext);
          const spec = EVOLVEPRO_CSV_SCHEMA;
          const validation = validateCsvHeader(header, spec);
          if (!validation.valid) {
            const detail = validation.errors.join("; ");
            set({
              statusMessage: i18next.t("inputSlice.csvFormatError", { mode: modeLabel, detail }),
              evolveproCsvPath: "",
            });
            return;
          }
        } catch {
          // 파일 읽기 실패 시 sidecar 에 위임 (경로 오류는 sidecar가 처리)
        }
      }

      const usePipeline = evolveproMode !== "topN";
        const params = buildEvolveproLoadParams({
          filepath,
          topN: effectiveTopN,
          usePipeline,
          evolveproMode,
          evolveproVariantColumn: activeVariantColumn,
          evolveproScoreColumn: activeScoreColumn,
          evolveproScoreOrder: activeScoreOrder,
          evolveproSheetName: activeSheetName,
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
          structureAccession: get().uniprotAccession,
          evolveproRound,
          roundSize,
          refSeq,
        });
      const result = await sendRequest("load_evolvepro_csv", params);
      if (gen !== csvLoadGeneration) return;
      const update = buildEvolveproLoadStateUpdate({
        result,
        currentMode: get().mutationInputMode,
        maxPerPosition,
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
        statusMessage: update.statusMessage,
        evolveproRankedCandidates: result.ranked_candidates ?? [],
        // Initialize selection directly from result.variants (pipeline source-of-truth).
        // ranked_candidates is guaranteed to contain all selected variants (backend invariant:
        // selected ⊆ ranked_candidates), but we seed from result.variants for authority clarity.
        evolveproSelectedVariants: result.variants ?? [],
        ...(isOthersMode && {
          othersUsedVariantColumn: result.used_variant_column ?? null,
          othersUsedScoreColumn: result.used_score_column ?? null,
        }),
      });

      // Dual-write to MAME shared store so other panels can auto-fill.
      try {
        useMameAppStore.getState().setSharedEvolveproCsvPath(filepath);
      } catch {
        // Defensive: never let the cross-store hand-off break CSV load.
      }
    } catch (err) {
      if (gen === csvLoadGeneration) {
        const modeLabel = get().evolveproMode === "others" ? "Others" : "EVOLVEpro";
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
    // Switching modes changes which params are sent; reload CSV if loaded.
    const path = mode === "others" ? "" : get().evolveproCsvPath;
    if (path) {
      void get().loadEvolveproCsv(path);
    }
  },
  setEvolveproVariantColumn: (col) => set({ evolveproVariantColumn: col }),
  setEvolveproScoreColumn: (col) => set({ evolveproScoreColumn: col }),
  setEvolveproScoreOrder: (order) => set({ evolveproScoreOrder: order }),
  setEvolveproSheetName: (name) => set({ evolveproSheetName: name }),
  setEvolveproPreview: (preview) => set({ evolveproPreview: preview }),
  setOthersSourcePath: (path) => set({
    othersSourcePath: path,
    othersUsedVariantColumn: null,
    othersUsedScoreColumn: null,
  }),
  setOthersVariantColumn: (col) => set({ othersVariantColumn: col, othersUsedVariantColumn: null }),
  setOthersScoreColumn: (col) => set({ othersScoreColumn: col, othersUsedScoreColumn: null }),
  setOthersScoreOrder: (order) => set({ othersScoreOrder: order }),
  setOthersSheetName: (name) => set({ othersSheetName: name }),
  setOthersPreview: (preview) => set({ othersPreview: preview }),

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
