import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import { useMameAppStore } from "../mame/mameAppStore";

import type { SequenceSlice } from "../slice-interfaces";
export type { SequenceSlice };

// Only domain/pareto/structural diversity actually consume uniprotAccession
// (reference-domain fetch, pareto 3D distance, structural diversity, 3D view).
// Top-N-only workflows never touch it, so BLAST-backed auto-search (slow, no
// known accession) is gated on at least one of these being enabled.
function diversityConsumersEnabled(state: AppState): boolean {
  return state.domainDiversityEnabled || state.paretoDiversityEnabled || state.structuralDiversityEnabled;
}

const UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE =
  "UniProt auto-search skipped (domain/pareto/structural diversity disabled), "
  + "use the Step 1 search button if you need it later.";

export const createSequenceSlice: StateCreator<AppState, [], [], SequenceSlice> = (set, get) => ({
  fastaPath: "",
  seqInfo: null,
  selectedGene: "",
  organism: "ecoli",

  loadSequence: async (filepath: string) => {
    try {
      set({ statusMessage: "Loading sequence file..." });
      const info = await sendRequest("load_fasta", { filepath });

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
        domains: [],
        refDomains: [],
        refDomainHash: "",
        refDomainsLoading: false,
        disabledDomains: [],
        domainStats: {},
        domainLoading: false,
        poolVariants: [],
        benchmarkResults: null,
        showBenchmark: false,
        uniprotCandidates: [],
        uniprotSearching: false,
        uniprotAccession: "",
        structureAccession: "",
        structureLoaded: false,
        structureLoading: false,
        statusMessage: `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) | Target: ${bestGene?.gene ?? "none"}`,
      });

      // Dual-write to MAME shared store so BarcodeSetupPanel can auto-fill.
      try {
        useMameAppStore.getState().setSharedFastaPath(filepath);
      } catch {
        // Defensive: never let the cross-store hand-off break sequence load.
      }

      // Auto-trigger UniProt search if gene has db_xref or translation.
      // Known-accession lookups are cheap (backend skips BLAST at >=95%
      // identity), so those always run. BLAST-only lookups (no known
      // accession) are gated on an actual accession consumer being enabled.
      if (bestGene) {
        const knownAcc = bestGene.uniprot_accession ?? "";
        const translation = bestGene.translation ?? "";
        const organism = bestGene.organism ?? "";
        if (knownAcc) {
          get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
        } else if (translation) {
          if (diversityConsumersEnabled(get())) {
            get().searchUniprot(bestGene.gene, organism, translation, knownAcc);
          } else {
            set({ statusMessage: UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE });
          }
        }
      }
    } catch (err) {
      set({ statusMessage: `Sequence file load failed: ${formatError(err)}` });
    }
  },

  setSelectedGene: (gene: string) => {
    set({
      selectedGene: gene,
      domains: [],
      refDomains: [],
      refDomainHash: "",
      refDomainsLoading: false,
      disabledDomains: [],
      domainStats: {},
      domainLoading: false,
      poolVariants: [],
      benchmarkResults: null,
      showBenchmark: false,
      uniprotCandidates: [],
      uniprotSearching: false,
      uniprotAccession: "",
      structureAccession: "",
      structureLoaded: false,
      structureLoading: false,
    });
    const { seqInfo, organism } = get();
    const g = seqInfo?.genes.find((g) => String(g.cds_start) === gene);
    if (g) {
      const knownAcc = g.uniprot_accession ?? "";
      const translation = g.translation ?? "";
      if (knownAcc) {
        get().searchUniprot(g.gene, g.organism ?? organism, translation, knownAcc);
      } else if (translation) {
        if (diversityConsumersEnabled(get())) {
          get().searchUniprot(g.gene, g.organism ?? organism, translation, knownAcc);
        } else {
          set({ statusMessage: UNIPROT_AUTO_SEARCH_SKIPPED_MESSAGE });
        }
      }
    }
  },

  setOrganism: (organism: string) => set({ organism }),
});
