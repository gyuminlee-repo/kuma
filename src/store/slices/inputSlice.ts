import type { StateCreator } from "zustand";
import { resolveResource } from "@tauri-apps/api/path";
import { sendRequest } from "../../lib/ipc";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  SequenceInfo,
  ParsedMutation,
  ParseError,
  ParseMutationsResult,
  EvolveproLoadResult,
  DomainInfo,
  FetchDomainsResult,
  UniprotCandidate,
  SearchUniprotResult,
  EsmEmbeddingResult,
} from "../../types/models";

export interface InputSlice {
  // State
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  mutationInputMode: "text" | "evolvepro" | "multi-evolve";
  mutationText: string;
  evolveproCsvPath: string;
  yPredMap: Record<string, number>;
  pipelineMode: boolean;
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  domainDiversityEnabled: boolean;
  domainStrategy: "proportional" | "equal";
  uniprotAccession: string;
  domains: DomainInfo[];
  domainLoading: boolean;
  disabledDomains: Set<string>;
  domainStats: Record<string, { quota: number; selected: number }>;
  paretoDiversityEnabled: boolean;
  entropyWeightEnabled: boolean;
  esmEmbeddingLoaded: boolean;
  esmEmbeddingLoading: boolean;
  parsedMutations: ParsedMutation[];
  parseErrors: ParseError[];
  selectedGene: string;
  organism: string;
  uniprotCandidates: UniprotCandidate[];
  uniprotSearching: boolean;
  evolveproTotalCount: number;

  // Actions
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setOrganism: (organism: string) => void;
  setMutationInputMode: (mode: "text" | "evolvepro" | "multi-evolve") => void;
  setMutationText: (text: string) => void;
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
  fetchEsmEmbedding: (accession: string, sequence?: string) => Promise<void>;
  loadEvolveproCsv: (filepath: string) => Promise<void>;
  parseMutations: () => Promise<void>;
  searchUniprot: (geneName: string, organism: string, translation: string, knownAccession: string) => Promise<void>;
  loadSampleData: () => Promise<void>;
}

let csvLoadGeneration = 0;

// Debounce timer for pipeline option changes to prevent RPC request bursts
let reloadTimer: ReturnType<typeof setTimeout> | null = null;

function debouncedReload(get: () => AppState) {
  if (reloadTimer) clearTimeout(reloadTimer);
  reloadTimer = setTimeout(() => {
    reloadTimer = null;
    const state = get();
    if (state.evolveproCsvPath) {
      state.loadEvolveproCsv(state.evolveproCsvPath);
    }
  }, 300);
}

export const createInputSlice: StateCreator<AppState, [], [], InputSlice> = (set, get) => ({
  fastaPath: "",
  seqInfo: null,
  mutationInputMode: "text",
  mutationText: "",
  evolveproCsvPath: "",
  yPredMap: {},
  pipelineMode: true,
  positionDiversityEnabled: true,
  maxPerPosition: 1,
  domainDiversityEnabled: true,
  domainStrategy: "proportional",
  uniprotAccession: "",
  domains: [],
  domainLoading: false,
  disabledDomains: new Set<string>(),
  domainStats: {},
  paretoDiversityEnabled: true,
  entropyWeightEnabled: true,
  esmEmbeddingLoaded: false,
  esmEmbeddingLoading: false,
  parsedMutations: [],
  parseErrors: [],
  selectedGene: "",
  organism: "ecoli",
  uniprotCandidates: [],
  uniprotSearching: false,
  evolveproTotalCount: 0,

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
  setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
  setMutationText: (text) => set({ mutationText: text }),

  setPipelineMode: (enabled: boolean) => {
    set({ pipelineMode: enabled });
    if (!enabled) {
      // Pipeline off -> Top-N only: reload with no diversity options
      debouncedReload(get);
    }
  },

  setPositionDiversityEnabled: (enabled: boolean) => {
    set({ positionDiversityEnabled: enabled });
    debouncedReload(get);
  },

  setMaxPerPosition: (n: number) => {
    set({ maxPerPosition: Math.max(1, n) });
    debouncedReload(get);
  },

  setDomainDiversityEnabled: (enabled: boolean) => {
    set({ domainDiversityEnabled: enabled });
    debouncedReload(get);
  },

  setDomainStrategy: (strategy: "proportional" | "equal") => {
    set({ domainStrategy: strategy });
    debouncedReload(get);
  },

  fetchDomains: async (accession: string, clearCandidates = false) => {
    set({
      domainLoading: true,
      ...(clearCandidates && { uniprotCandidates: [] }),
      statusMessage: "Fetching domain info...",
    });
    try {
      const result = await sendRequest<FetchDomainsResult>("fetch_domains", { accession });
      set({
        uniprotAccession: accession,
        domains: result.domains,
        disabledDomains: new Set<string>(),
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
    set({ domains, disabledDomains: new Set<string>() });
    const { evolveproCsvPath, domainDiversityEnabled } = get();
    if (evolveproCsvPath && domainDiversityEnabled) get().loadEvolveproCsv(evolveproCsvPath);
  },

  toggleDomain: (domainKey: string) => {
    const next = new Set(get().disabledDomains);
    if (next.has(domainKey)) next.delete(domainKey);
    else next.add(domainKey);
    set({ disabledDomains: next });
    debouncedReload(get);
  },

  setParetoDiversityEnabled: (enabled: boolean) => {
    set({ paretoDiversityEnabled: enabled });
    debouncedReload(get);
  },

  setEntropyWeightEnabled: (enabled: boolean) => {
    set({ entropyWeightEnabled: enabled });
    debouncedReload(get);
  },

  fetchEsmEmbedding: async (accession: string, sequence?: string) => {
    set({ esmEmbeddingLoading: true, statusMessage: "ESM-2 embedding loading..." });
    try {
      const result = await sendRequest<EsmEmbeddingResult>("fetch_esm_embedding", { accession, sequence: sequence ?? "" });
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

  loadEvolveproCsv: async (filepath: string) => {
    const gen = ++csvLoadGeneration;
    try {
      const { pipelineMode, positionDiversityEnabled, maxPerPosition, domainDiversityEnabled, domains, disabledDomains, domainStrategy, paretoDiversityEnabled, entropyWeightEnabled, maxPrimers } = get();
      const activeDomains = domains.filter((d) => !disabledDomains.has(`${d.name}-${d.start}`));
      const modeLabel = get().mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro";
      set({ statusMessage: `Loading ${modeLabel} CSV...`, evolveproCsvPath: filepath });
      const result = await sendRequest<EvolveproLoadResult>(
        "load_evolvepro_csv",
        {
          filepath,
          top_n: maxPrimers,
          ...(pipelineMode && positionDiversityEnabled && { max_per_position: maxPerPosition }),
          ...(pipelineMode && domainDiversityEnabled && activeDomains.length > 0 && {
            domain_diversity: true,
            domains: activeDomains.map((d) => ({ name: d.name, start: d.start, end: d.end })),
            domain_strategy: domainStrategy,
          }),
          ...(pipelineMode && paretoDiversityEnabled && { pareto_diversity: true }),
          ...(pipelineMode && paretoDiversityEnabled && entropyWeightEnabled && { entropy_weight: 0.3 }),
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

  searchUniprot: async (geneName: string, organism: string, translation: string, knownAccession: string) => {
    set({ uniprotSearching: true, statusMessage: "UniProt BLAST search in progress..." });
    try {
      const result = await sendRequest<SearchUniprotResult>("search_uniprot", {
        gene_name: geneName,
        organism,
        translation,
        known_accession: knownAccession,
      });
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
