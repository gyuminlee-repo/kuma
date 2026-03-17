import { create } from "zustand";
import { sendRequest, setProgressHandler } from "../lib/ipc";

function formatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
import type {
  PolymeraseInfo,
  SequenceInfo,
  ParsedMutation,
  SdmPrimerResult,
  DesignResult,
  FailedMutation,
  PlateMapping,
  PlateMapResult,
  EvolveproLoadResult,
} from "../types/models";

interface AppState {
  // Sidecar
  polymerases: PolymeraseInfo[];

  // Input
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  mutationInputMode: "text" | "evolvepro";
  mutationText: string;
  evolveproCsvPath: string;
  parsedMutations: ParsedMutation[];

  // Parameters
  selectedGene: string;
  selectedPolymerase: string;

  // Design
  isDesigning: boolean;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];

  // Plate Map
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;

  // UI
  progress: number;
  statusMessage: string;

  // Actions
  fetchPolymerases: () => Promise<void>;
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setMutationInputMode: (mode: "text" | "evolvepro") => void;
  setMutationText: (text: string) => void;
  loadEvolveproCsv: (filepath: string) => Promise<void>;
  setSelectedPolymerase: (name: string) => void;
  parseMutations: () => Promise<void>;
  designPrimers: () => Promise<void>;
  getAlternatives: (mutation: string) => Promise<SdmPrimerResult[]>;
  swapPrimer: (mutation: string, candidateIdx: number) => Promise<void>;
  getPlateMap: () => Promise<void>;
  exportTsv: (filepath: string) => Promise<void>;
  exportExcel: (filepath: string) => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => {
  setProgressHandler((p) => {
    set({ progress: p.value, statusMessage: p.message });
  });

  return {
    polymerases: [],
    fastaPath: "",
    seqInfo: null,
    mutationInputMode: "text",
    mutationText: "",
    evolveproCsvPath: "",
    parsedMutations: [],
    selectedGene: "",
    selectedPolymerase: "KOD",
    isDesigning: false,
    designResults: [],
    successCount: 0,
    totalCount: 0,
    failedMutations: [],
    plateMappings: [],
    dedupInfo: {},
    progress: 0,
    statusMessage: "Ready",

    fetchPolymerases: async () => {
      try {
        const list = await sendRequest<PolymeraseInfo[]>("list_polymerases");
        set({ polymerases: list });
      } catch (err) {
        console.error("Failed to fetch polymerases:", err);
      }
    },

    loadSequence: async (filepath: string) => {
      try {
        set({ statusMessage: "Loading sequence file..." });
        const info = await sendRequest<SequenceInfo>("load_fasta", { filepath });

        // Auto-select: pick gene with longest aa_length
        let bestGene = info.genes.length > 0 ? info.genes[0] : null;
        if (info.genes.length > 1) {
          for (const g of info.genes) {
            if (!bestGene || g.aa_length > bestGene.aa_length) {
              bestGene = g;
            }
          }
        }

        const selectedKey = bestGene ? String(bestGene.cds_start) : "";
        set({
          fastaPath: filepath,
          seqInfo: info,
          selectedGene: selectedKey,
          statusMessage: `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) | Target: ${bestGene?.gene ?? "none"}`,
        });
      } catch (err) {
        set({ statusMessage: `Sequence file load failed: ${formatError(err)}` });
      }
    },

    setSelectedGene: (gene: string) => set({ selectedGene: gene }),
    setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
    setMutationText: (text) => set({ mutationText: text }),

    loadEvolveproCsv: async (filepath: string) => {
      try {
        set({ statusMessage: "Loading EVOLVEpro CSV...", evolveproCsvPath: filepath });
        const result = await sendRequest<EvolveproLoadResult>(
          "load_evolvepro_csv",
          { filepath, top_n: 96 },
        );
        const variantText = result.variants.join("\n");
        set({
          mutationText: variantText,
          mutationInputMode: "evolvepro",
          statusMessage: `EVOLVEpro: ${result.selected_count}/${result.total_count} variants loaded (top-96 by y_pred)`,
        });
      } catch (err) {
        set({ statusMessage: `EVOLVEpro CSV load failed: ${formatError(err)}` });
      }
    },
    setSelectedPolymerase: (name) => set({ selectedPolymerase: name }),

    parseMutations: async () => {
      const { mutationText } = get();
      try {
        const parsed = await sendRequest<ParsedMutation[]>(
          "parse_mutations_text",
          { text: mutationText },
        );
        set({ parsedMutations: parsed });
      } catch (err) {
        set({ statusMessage: `Mutation parse failed: ${formatError(err)}` });
      }
    },

    designPrimers: async () => {
      const {
        fastaPath,
        selectedGene,
        mutationText,
        selectedPolymerase,
      } = get();

      if (!fastaPath) {
        set({ statusMessage: "Sequence file not loaded" });
        return;
      }
      if (!mutationText.trim()) {
        set({ statusMessage: "No mutations entered" });
        return;
      }

      // Resolve CDS start from selected gene (selectedGene stores cds_start as string)
      const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;

      set({
        isDesigning: true,
        progress: 0,
        statusMessage: "Designing primers...",
        designResults: [],
        plateMappings: [],
      });

      try {
        const result = await sendRequest<DesignResult>("design_sdm_primers", {
          fasta_path: fastaPath,
          target_start: targetStart,
          mutations_csv_or_text: mutationText,
          polymerase: selectedPolymerase,
        });

        set({
          designResults: result.results,
          successCount: result.success_count,
          totalCount: result.total_count,
          failedMutations: result.failed_mutations ?? [],
          statusMessage: `${result.success_count}/${result.total_count} designed | Tm condition: ${result.results.filter((r) => r.tm_condition_met).length}/${result.success_count}`,
        });

        // Auto-fetch plate map (non-fatal)
        try {
          const plateResult =
            await sendRequest<PlateMapResult>("get_plate_map");
          set({
            plateMappings: plateResult.mappings,
            dedupInfo: plateResult.dedup_info,
          });
        } catch (plateErr) {
          console.warn("[plate map]", formatError(plateErr));
        }
      } catch (err) {
        set({ statusMessage: `Design failed: ${formatError(err)}` });
      } finally {
        set({ isDesigning: false, progress: 100 });
      }
    },

    getAlternatives: async (mutation: string) => {
      const result = await sendRequest<{ candidates: SdmPrimerResult[] }>(
        "get_alternatives",
        { mutation },
      );
      return result.candidates;
    },

    swapPrimer: async (mutation: string, candidateIdx: number) => {
      const updated = await sendRequest<SdmPrimerResult>(
        "swap_primer",
        { mutation, candidate_idx: candidateIdx },
      );
      const { designResults } = get();
      set({
        designResults: designResults.map((r) =>
          r.mutation === mutation ? updated : r
        ),
      });
    },

    getPlateMap: async () => {
      try {
        const result = await sendRequest<PlateMapResult>("get_plate_map");
        set({
          plateMappings: result.mappings,
          dedupInfo: result.dedup_info,
        });
      } catch (err) {
        set({ statusMessage: `Plate map failed: ${formatError(err)}` });
      }
    },

    exportTsv: async (filepath: string) => {
      try {
        await sendRequest("export_tsv", { filepath });
        set({ statusMessage: `Exported TSV: ${filepath}` });
      } catch (err) {
        set({ statusMessage: `TSV export failed: ${formatError(err)}` });
      }
    },

    exportExcel: async (filepath: string) => {
      try {
        await sendRequest("export_excel", { filepath });
        set({ statusMessage: `Exported Excel: ${filepath}` });
      } catch (err) {
        set({ statusMessage: `Excel export failed: ${formatError(err)}` });
      }
    },
  };
});
