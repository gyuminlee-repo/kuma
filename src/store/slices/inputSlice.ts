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
  MULTI_EVOLVE_CSV_SCHEMA,
} from "../../lib/schemaValidator";

import type { InputSlice } from "../slice-interfaces";
export type { InputSlice };

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => {
  let csvLoadGeneration = 0;

  return ({
  mutationInputMode: "text",
  mutationText: "",
  parsedMutations: [],
  parseErrors: [],
  evolveproCsvPath: "",
  evolveproTotalCount: 0,
  evolveproFilteredCount: null,
  evolveproParetoExchanges: null,
  evolveproStepStats: null,
  yPredMap: {},

  setMutationInputMode: (mode) => set({
    mutationInputMode: mode,
    ...(mode === "text" && {
      evolveproCsvPath: "",
      evolveproTotalCount: 0,
      evolveproFilteredCount: null,
      evolveproParetoExchanges: null,
      evolveproStepStats: null,
      yPredMap: {},
      domainStats: {},
      poolVariants: [],
    }),
  }),
  setMutationText: (text) => set({ mutationText: text }),

  loadEvolveproCsv: async (filepath: string, topNOverride?: number) => {
    const gen = ++csvLoadGeneration;
    try {
      const {
        pipelineMode,
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
      const isMultiEvolve = get().mutationInputMode === "multi-evolve";
      const modeLabel = isMultiEvolve ? "MULTI-evolve" : "EVOLVEpro";
      set({ statusMessage: `Loading ${modeLabel} CSV...`, evolveproCsvPath: filepath });

      // §3 Input Guards: sidecar 호출 전 헤더 컬럼 검증
      try {
        const csvText = await readTextFile(filepath);
        const header = extractCsvHeader(csvText);
        const spec = isMultiEvolve ? MULTI_EVOLVE_CSV_SCHEMA : EVOLVEPRO_CSV_SCHEMA;
        const validation = validateCsvHeader(header, spec);
        if (!validation.valid) {
          const detail = validation.errors.join("; ");
          set({
            statusMessage: `${modeLabel} CSV 형식 오류: ${detail}`,
            evolveproCsvPath: "",
          });
          return;
        }
      } catch {
        // 파일 읽기 실패 시 sidecar 에 위임 (경로 오류는 sidecar가 처리)
      }

      const usePipeline = pipelineMode && !isMultiEvolve;
        const params = buildEvolveproLoadParams({
          filepath,
          topN: effectiveTopN,
          usePipeline,
          isMultiEvolve,
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
      const currentMode = get().mutationInputMode;
      set({
        mutationText: update.mutationText,
        mutationInputMode: currentMode === "multi-evolve" ? "multi-evolve" : "evolvepro",
        yPredMap: update.yPredMap,
        domainStats: update.domainStats,
        poolVariants: update.poolVariants,
        evolveproTotalCount: update.evolveproTotalCount,
        evolveproFilteredCount: update.evolveproFilteredCount,
        evolveproParetoExchanges: update.evolveproParetoExchanges,
        evolveproStepStats: update.evolveproStepStats,
        statusMessage: update.statusMessage,
      });
    } catch (err) {
      if (gen === csvLoadGeneration) {
        set({
          mutationText: "",
          evolveproTotalCount: 0,
          evolveproFilteredCount: null,
          evolveproParetoExchanges: null,
          evolveproStepStats: null,
          yPredMap: {},
          domainStats: {},
          poolVariants: [],
          statusMessage: `${get().mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"} CSV load failed: ${formatError(err)}`,
        });
      }
      throw err;
    }
  },

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
    try {
      set({ statusMessage: "Loading sample data..." });
      const mode = get().mutationInputMode;
      const csvFilename =
        mode === "multi-evolve"
          ? "samples/sample_multi_evolve.csv"
          : "samples/sample_evolvepro.csv";
      const [gbPath, csvPath] = await Promise.all([
        resolveResource("samples/sample_plasmid.gb"),
        resolveResource(csvFilename),
      ]);
      await get().loadSequence(gbPath);
      await get().loadEvolveproCsv(csvPath);
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
      statusMessage: `Round ${prevRound.n} activity loaded: ${filtered.length} variants (EVOLVEpro mode)`,
    });

    return { ok: true, warnings };
  },
});
};
