import { create } from "zustand";
import { sendRequest, setProgressHandler } from "../lib/ipc";
import type {
  PolymeraseInfo,
  FastaInfo,
  ParsedMutation,
  SdmPrimerResult,
  DesignResult,
  PlateMapping,
  PlateMapResult,
} from "../types/models";

interface AppState {
  // Sidecar
  polymerases: PolymeraseInfo[];

  // Input
  fastaPath: string;
  fastaInfo: FastaInfo | null;
  mutationInputMode: "text" | "csv";
  mutationText: string;
  mutationCsvPath: string;
  parsedMutations: ParsedMutation[];

  // Parameters
  cdsStart: number;
  selectedPolymerase: string;
  overlapLen: number;

  // Design
  isDesigning: boolean;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;

  // Plate Map
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;

  // UI
  progress: number;
  statusMessage: string;

  // Actions
  fetchPolymerases: () => Promise<void>;
  loadFasta: (filepath: string) => Promise<void>;
  setCdsStart: (start: number) => void;
  setMutationInputMode: (mode: "text" | "csv") => void;
  setMutationText: (text: string) => void;
  setMutationCsvPath: (path: string) => void;
  setSelectedPolymerase: (name: string) => void;
  setOverlapLen: (len: number) => void;
  parseMutations: () => Promise<void>;
  designPrimers: () => Promise<void>;
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
    fastaInfo: null,
    mutationInputMode: "text",
    mutationText: "",
    mutationCsvPath: "",
    parsedMutations: [],
    cdsStart: 0,
    selectedPolymerase: "KOD",
    overlapLen: 20,
    isDesigning: false,
    designResults: [],
    successCount: 0,
    totalCount: 0,
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

    loadFasta: async (filepath: string) => {
      try {
        set({ statusMessage: "Loading FASTA..." });
        const info = await sendRequest<FastaInfo>("load_fasta", { filepath });

        // Auto-select: pick ATG with longest downstream ORF (no in-frame stop within sequence)
        let bestAtg = info.atg_positions.length > 0 ? info.atg_positions[0] : 0;
        if (info.atg_positions.length > 1 && info.orf_lengths) {
          // sidecar provides orf_lengths parallel to atg_positions
          let maxLen = 0;
          for (let i = 0; i < info.atg_positions.length; i++) {
            const orfLen = info.orf_lengths[i] ?? 0;
            if (orfLen > maxLen) {
              maxLen = orfLen;
              bestAtg = info.atg_positions[i];
            }
          }
        }

        set({
          fastaPath: filepath,
          fastaInfo: info,
          cdsStart: bestAtg,
          statusMessage: `Loaded: ${info.header} (${info.seq_length} bp) — CDS Start auto-selected: ${bestAtg}`,
        });
      } catch (err) {
        set({ statusMessage: `FASTA load failed: ${String(err)}` });
      }
    },

    setCdsStart: (start: number) => set({ cdsStart: start }),
    setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
    setMutationText: (text) => set({ mutationText: text }),
    setMutationCsvPath: (path) => set({ mutationCsvPath: path }),
    setSelectedPolymerase: (name) => set({ selectedPolymerase: name }),
    setOverlapLen: (len) => set({ overlapLen: len }),

    parseMutations: async () => {
      const { mutationText } = get();
      try {
        const parsed = await sendRequest<ParsedMutation[]>(
          "parse_mutations_text",
          { text: mutationText },
        );
        set({ parsedMutations: parsed });
      } catch (err) {
        set({ statusMessage: `Mutation parse failed: ${err instanceof Error ? err.message : String(err)}` });
      }
    },

    designPrimers: async () => {
      const {
        fastaPath,
        cdsStart,
        mutationInputMode,
        mutationText,
        mutationCsvPath,
        selectedPolymerase,
        overlapLen,
      } = get();

      if (!fastaPath) {
        set({ statusMessage: "FASTA file not loaded" });
        return;
      }

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
          target_start: cdsStart,
          mutations_csv_or_text:
            mutationInputMode === "text" ? mutationText : mutationCsvPath,
          polymerase: selectedPolymerase,
          overlap_len: overlapLen,
        });

        set({
          designResults: result.results,
          successCount: result.success_count,
          totalCount: result.total_count,
          statusMessage: `${result.success_count}/${result.total_count} designed | Tm condition: ${result.results.filter((r) => r.tm_condition_met).length}/${result.success_count}`,
        });

        // Auto-fetch plate map
        const plateResult =
          await sendRequest<PlateMapResult>("get_plate_map");
        set({
          plateMappings: plateResult.mappings,
          dedupInfo: plateResult.dedup_info,
        });
      } catch (err) {
        set({ statusMessage: `Design failed: ${err instanceof Error ? err.message : String(err)}` });
      } finally {
        set({ isDesigning: false, progress: 100 });
      }
    },

    getPlateMap: async () => {
      try {
        const result = await sendRequest<PlateMapResult>("get_plate_map");
        set({
          plateMappings: result.mappings,
          dedupInfo: result.dedup_info,
        });
      } catch (err) {
        set({ statusMessage: `Plate map failed: ${err instanceof Error ? err.message : String(err)}` });
      }
    },

    exportTsv: async (filepath: string) => {
      try {
        await sendRequest("export_tsv", { filepath });
        set({ statusMessage: `Exported TSV: ${filepath}` });
      } catch (err) {
        set({ statusMessage: `TSV export failed: ${err instanceof Error ? err.message : String(err)}` });
      }
    },

    exportExcel: async (filepath: string) => {
      try {
        await sendRequest("export_excel", { filepath });
        set({ statusMessage: `Exported Excel: ${filepath}` });
      } catch (err) {
        set({ statusMessage: `Excel export failed: ${err instanceof Error ? err.message : String(err)}` });
      }
    },
  };
});
