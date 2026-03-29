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
} from "../../types/models";

export interface InputSlice {
  // State
  mutationInputMode: "text" | "evolvepro" | "multi-evolve";
  mutationText: string;
  parsedMutations: ParsedMutation[];
  parseErrors: ParseError[];
  evolveproCsvPath: string;
  evolveproTotalCount: number;
  yPredMap: Record<string, number>;

  // Actions
  setMutationInputMode: (mode: "text" | "evolvepro" | "multi-evolve") => void;
  setMutationText: (text: string) => void;
  parseMutations: () => Promise<void>;
  loadEvolveproCsv: (filepath: string) => Promise<void>;
  loadSampleData: () => Promise<void>;
}

let csvLoadGeneration = 0;

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => ({
  mutationInputMode: "text",
  mutationText: "",
  parsedMutations: [],
  parseErrors: [],
  evolveproCsvPath: "",
  evolveproTotalCount: 0,
  yPredMap: {},

  setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
  setMutationText: (text) => set({ mutationText: text }),

  loadEvolveproCsv: async (filepath: string) => {
    const gen = ++csvLoadGeneration;
    try {
      const { pipelineMode, positionDiversityEnabled, maxPerPosition, domainDiversityEnabled, domains, disabledDomains, domainStrategy, paretoDiversityEnabled, entropyWeightEnabled, maxPrimers } = get();
      const activeDomains = domains.filter((d) => !disabledDomains.has(`${d.name}-${d.start}`));
      const isMultiEvolve = get().mutationInputMode === "multi-evolve";
      const modeLabel = isMultiEvolve ? "MULTI-evolve" : "EVOLVEpro";
      set({ statusMessage: `Loading ${modeLabel} CSV...`, evolveproCsvPath: filepath });
      // MULTI-evolve: skip diversity pipeline — combinations are pre-selected
      const usePipeline = pipelineMode && !isMultiEvolve;
      const result = await sendRequest<EvolveproLoadResult>(
        "load_evolvepro_csv",
        {
          filepath,
          top_n: isMultiEvolve ? 0 : maxPrimers,
          ...(usePipeline && positionDiversityEnabled && { max_per_position: maxPerPosition }),
          ...(usePipeline && domainDiversityEnabled && activeDomains.length > 0 && {
            domain_diversity: true,
            domains: activeDomains.map((d) => ({ name: d.name, start: d.start, end: d.end })),
            domain_strategy: domainStrategy,
          }),
          ...(usePipeline && paretoDiversityEnabled && { pareto_diversity: true }),
          ...(usePipeline && paretoDiversityEnabled && entropyWeightEnabled && { entropy_weight: 0.3 }),
        },
      );
      if (gen !== csvLoadGeneration) return;
      const yMap: Record<string, number> = {};
      result.variants.forEach((v, i) => { yMap[v] = result.y_preds[i] ?? 0; });
      const variantText = result.variants.join("\n");
      const filteredMsg = result.filtered_count
        ? ` (${result.filtered_count} filtered, max ${maxPerPosition}/pos)`
        : "";
      const domainMsg = result.domain_stats
        ? " | " + Object.entries(result.domain_stats).map(([name, s]) =>
            s.selected < s.quota
              ? `${name}: ${s.selected}/${s.quota} \u26A0`
              : `${name}: ${s.selected}/${s.quota}`
          ).join(", ")
        : "";
      const paretoMsg = result.pareto_replaced != null && result.pareto_replaced > 0
        ? ` | Pareto: ${result.pareto_replaced} diversified`
        : "";
      // Clamp maxPrimers to CSV variant count
      if (result.total_count > 0 && maxPrimers > result.total_count) {
        get().setMaxPrimers(result.total_count);
      }
      const currentMode = get().mutationInputMode;
      set({
        mutationText: variantText,
        mutationInputMode: currentMode === "multi-evolve" ? "multi-evolve" : "evolvepro",
        yPredMap: yMap,
        domainStats: result.domain_stats ?? {},
        evolveproTotalCount: result.total_count,
        statusMessage: `${currentMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"}: ${result.selected_count}/${result.total_count} variants${filteredMsg}${domainMsg}${paretoMsg}`,
      });
    } catch (err) {
      if (gen === csvLoadGeneration) {
        set({ statusMessage: `${get().mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"} CSV load failed: ${formatError(err)}` });
      }
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
      const [gbPath, csvPath] = await Promise.all([
        resolveResource("samples/sample_plasmid.gb"),
        resolveResource("samples/sample_evolvepro.csv"),
      ]);
      await get().loadSequence(gbPath);
      set({ mutationInputMode: "evolvepro" });
      await get().loadEvolveproCsv(csvPath);
    } catch (err) {
      set({ statusMessage: `Sample load failed: ${formatError(err)}` });
    }
  },
});
