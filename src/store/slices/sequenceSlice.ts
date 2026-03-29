import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type { SequenceInfo } from "../../types/models";

export interface SequenceSlice {
  // State
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  selectedGene: string;
  organism: string;

  // Actions
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setOrganism: (organism: string) => void;
}

export const createSequenceSlice: StateCreator<AppState, [], [], SequenceSlice> = (set, get) => ({
  fastaPath: "",
  seqInfo: null,
  selectedGene: "",
  organism: "ecoli",

  loadSequence: async (filepath: string) => {
    try {
      set({ statusMessage: "Loading sequence file..." });
      const info = await sendRequest<SequenceInfo>("load_fasta", { filepath });

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
        uniprotCandidates: [],
        statusMessage: `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) | Target: ${bestGene?.gene ?? "none"}`,
      });

      // Auto-trigger UniProt search if gene has db_xref or translation
      if (bestGene) {
        const knownAcc = bestGene.uniprot_accession ?? "";
        const translation = bestGene.translation ?? "";
        const organism = bestGene.organism ?? "";
        if (knownAcc || translation) {
          get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
        }
      }
    } catch (err) {
      set({ statusMessage: `Sequence file load failed: ${formatError(err)}` });
    }
  },

  setSelectedGene: (gene: string) => {
    set({ selectedGene: gene, uniprotCandidates: [] });
    const { seqInfo, organism } = get();
    const g = seqInfo?.genes.find((g) => String(g.cds_start) === gene);
    if (g && (g.uniprot_accession || g.translation)) {
      get().searchUniprot(g.gene, g.organism ?? organism, g.translation ?? "", g.uniprot_accession ?? "");
    }
  },

  setOrganism: (organism: string) => set({ organism }),
});
