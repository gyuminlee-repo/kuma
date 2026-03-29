import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  DomainInfo,
  FetchDomainsResult,
  UniprotCandidate,
  SearchUniprotResult,
  EsmEmbeddingResult,
} from "../../types/models";

export interface DiversitySlice {
  // State
  pipelineMode: boolean;
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  domainDiversityEnabled: boolean;
  domainStrategy: "proportional" | "equal";
  uniprotAccession: string;
  domains: DomainInfo[];
  domainLoading: boolean;
  disabledDomains: string[];
  domainStats: Record<string, { quota: number; selected: number }>;
  paretoDiversityEnabled: boolean;
  entropyWeightEnabled: boolean;
  esmEmbeddingLoaded: boolean;
  esmEmbeddingLoading: boolean;
  uniprotCandidates: UniprotCandidate[];
  uniprotSearching: boolean;

  // Actions
  setPipelineMode: (enabled: boolean) => void;
  setPositionDiversityEnabled: (enabled: boolean) => void;
  setMaxPerPosition: (n: number) => void;
  setDomainDiversityEnabled: (enabled: boolean) => void;
  setDomainStrategy: (strategy: "proportional" | "equal") => void;
  fetchDomains: (accession: string, clearCandidates?: boolean) => Promise<void>;
  setDomains: (domains: DomainInfo[]) => void;
  toggleDomain: (domainKey: string) => void;
  setParetoDiversityEnabled: (enabled: boolean) => void;
  setEntropyWeightEnabled: (enabled: boolean) => void;
  searchUniprot: (geneName: string, organism: string, translation: string, knownAccession: string) => Promise<void>;
  fetchEsmEmbedding: (accession: string, sequence?: string) => Promise<void>;
  cancelDiversityReload: () => void;
}

export const createDiversitySlice: StateCreator<AppState, [], [], DiversitySlice> = (set, get) => {
  let reloadTimer: ReturnType<typeof setTimeout> | null = null;

  function debouncedReload() {
    if (reloadTimer) clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
      reloadTimer = null;
      const state = get();
      if (state.evolveproCsvPath) {
        state.loadEvolveproCsv(state.evolveproCsvPath);
      }
    }, 300);
  }

  return ({
  pipelineMode: true,
  positionDiversityEnabled: true,
  maxPerPosition: 1,
  domainDiversityEnabled: true,
  domainStrategy: "proportional",
  uniprotAccession: "",
  domains: [],
  domainLoading: false,
  disabledDomains: [] as string[],
  domainStats: {},
  paretoDiversityEnabled: true,
  entropyWeightEnabled: true,
  esmEmbeddingLoaded: false,
  esmEmbeddingLoading: false,
  uniprotCandidates: [],
  uniprotSearching: false,

  setPipelineMode: (enabled: boolean) => {
    set({ pipelineMode: enabled });
    if (!enabled) {
      // Pipeline off -> Top-N only: reload with no diversity options
      debouncedReload();
    }
  },

  setPositionDiversityEnabled: (enabled: boolean) => {
    set({ positionDiversityEnabled: enabled });
    debouncedReload();
  },

  setMaxPerPosition: (n: number) => {
    set({ maxPerPosition: Math.max(1, n) });
    debouncedReload();
  },

  setDomainDiversityEnabled: (enabled: boolean) => {
    set({ domainDiversityEnabled: enabled });
    debouncedReload();
  },

  setDomainStrategy: (strategy: "proportional" | "equal") => {
    set({ domainStrategy: strategy });
    debouncedReload();
  },

  fetchDomains: async (accession: string, clearCandidates = false) => {
    set({
      domainLoading: true,
      ...(clearCandidates && { uniprotCandidates: [] }),
      statusMessage: "Fetching domain info...",
    });
    try {
      const result = await sendRequest<FetchDomainsResult>("fetch_domains", { accession }, 120_000);
      set({
        uniprotAccession: accession,
        domains: result.domains,
        disabledDomains: [] as string[],
        domainLoading: false,
        statusMessage: result.domains.length > 0
          ? `Domains: ${result.domains.length} found (${result.source})`
          : result.error_msg ? `Domain fetch failed: ${result.error_msg}` : "No domains found",
      });
      const { evolveproCsvPath, esmEmbeddingLoaded } = get();
      if (evolveproCsvPath && result.domains.length > 0) get().loadEvolveproCsv(evolveproCsvPath);
      // Also fetch ESM embedding for manual accession entry
      if (!esmEmbeddingLoaded) {
        const gene = get().seqInfo?.genes.find((g) => String(g.cds_start) === get().selectedGene);
        get().fetchEsmEmbedding(accession, gene?.translation ?? "");
      }
    } catch (err) {
      set({ domainLoading: false, statusMessage: `Domain fetch failed: ${formatError(err)}` });
    }
  },

  setDomains: (domains: DomainInfo[]) => {
    set({ domains, disabledDomains: [] });
    const { evolveproCsvPath, domainDiversityEnabled } = get();
    if (evolveproCsvPath && domainDiversityEnabled) get().loadEvolveproCsv(evolveproCsvPath);
  },

  toggleDomain: (domainKey: string) => {
    const current = get().disabledDomains;
    const next = current.includes(domainKey)
      ? current.filter((k) => k !== domainKey)
      : [...current, domainKey];
    set({ disabledDomains: next });
    debouncedReload();
  },

  setParetoDiversityEnabled: (enabled: boolean) => {
    set({ paretoDiversityEnabled: enabled });
    debouncedReload();
  },

  setEntropyWeightEnabled: (enabled: boolean) => {
    set({ entropyWeightEnabled: enabled });
    debouncedReload();
  },

  searchUniprot: async (geneName: string, organism: string, translation: string, knownAccession: string) => {
    set({ uniprotSearching: true, statusMessage: "UniProt BLAST search in progress..." });
    try {
      const result = await sendRequest<SearchUniprotResult>("search_uniprot", {
        gene_name: geneName,
        organism,
        translation,
        known_accession: knownAccession,
      }, 120_000);
      // Auto-fill accession if a 100% match is found
      let statusMsg = "UniProt: no matching entries found";
      const acc = result.auto_selected ?? "";
      if (result.error_detail && result.candidates.length === 0) {
        statusMsg = `UniProt search error: ${result.error_detail}`;
      } else if (result.auto_selected) {
        statusMsg = `UniProt: auto-matched ${result.auto_selected} (100% identity)`;
      } else if (result.candidates.length > 0) {
        statusMsg = `UniProt: ${result.candidates.length} candidate(s) found — select manually`;
      }
      set({
        uniprotCandidates: result.candidates,
        uniprotSearching: false,
        ...(acc && { uniprotAccession: acc }),
        statusMessage: statusMsg,
      });
      // Auto-trigger ESM-2 embedding with protein sequence for local inference
      if (acc) {
        get().fetchEsmEmbedding(acc, translation);
      }
    } catch (err) {
      set({ uniprotSearching: false, statusMessage: `UniProt search failed: ${formatError(err)}` });
    }
  },

  fetchEsmEmbedding: async (accession: string, sequence?: string) => {
    set({ esmEmbeddingLoading: true, statusMessage: "ESM-2 embedding loading..." });
    try {
      const result = await sendRequest<EsmEmbeddingResult>("fetch_esm_embedding", { accession, sequence: sequence ?? "" }, 120_000);
      if (result.success) {
        set({
          esmEmbeddingLoaded: true,
          esmEmbeddingLoading: false,
          statusMessage: `ESM-2 embedding loaded: ${result.length} residues, ${result.dimension}D`,
        });
        // Re-trigger CSV selection with ESM embedding now available
        const { evolveproCsvPath } = get();
        if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
      } else {
        set({
          esmEmbeddingLoaded: false,
          esmEmbeddingLoading: false,
          statusMessage: `ESM-2 unavailable (using position distance) — ${result.error ?? "API offline"}`,
        });
      }
    } catch (err) {
      set({
        esmEmbeddingLoaded: false,
        esmEmbeddingLoading: false,
        statusMessage: `ESM-2 fetch failed: ${formatError(err)}`,
      });
    }
  },

  cancelDiversityReload: () => {
    if (reloadTimer) { clearTimeout(reloadTimer); reloadTimer = null; }
  },
});
};
