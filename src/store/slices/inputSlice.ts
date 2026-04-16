import type { StateCreator } from "zustand";
import { resolveResource } from "@tauri-apps/api/path";
import { sendRequest } from "../../lib/ipc";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  ParsedMutation,
  ParseError,
  ParseMutationsResult,
  EvolveproLoadResult,
  EvolveproStepStats,
} from "../../types/models";
import {
  buildEvolveproLoadParams,
  buildEvolveproLoadStateUpdate,
} from "./inputSlice.helpers";

export interface InputSlice {
  // State
  mutationInputMode: "text" | "evolvepro" | "multi-evolve";
  mutationText: string;
  parsedMutations: ParsedMutation[];
  parseErrors: ParseError[];
  evolveproCsvPath: string;
  evolveproTotalCount: number;
  evolveproFilteredCount: number | null;
  evolveproParetoExchanges: number | null;
  evolveproStepStats: EvolveproStepStats | null;
  yPredMap: Record<string, number>;

  // Actions
  setMutationInputMode: (mode: "text" | "evolvepro" | "multi-evolve") => void;
  setMutationText: (text: string) => void;
  parseMutations: () => Promise<void>;
  loadEvolveproCsv: (filepath: string, topNOverride?: number) => Promise<void>;
  loadSampleData: () => Promise<void>;
}

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
      const result = await sendRequest<EvolveproLoadResult>("load_evolvepro_csv", params);
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
      const result = await sendRequest<ParseMutationsResult>(
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
});
};
