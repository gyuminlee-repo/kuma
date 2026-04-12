import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  BenchmarkResult,
  DistanceMode,
  DomainOverlapPolicy,
  DomainInfo,
  FetchDomainsResult,
  LinkerHandling,
  UniprotCandidate,
  SearchUniprotResult,
  StructureResult,
} from "../../types/models";

export interface DiversitySlice {
  // State
  pipelineMode: boolean;
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  domainDiversityEnabled: boolean;
  domainStrategy: "proportional" | "equal";
  domainOverlapPolicy: DomainOverlapPolicy;
  linkerHandling: LinkerHandling;
  domainQuotaMin: number;
  uniprotAccession: string;
  domains: DomainInfo[];
  domainLoading: boolean;
  disabledDomains: string[];
  domainStats: Record<string, { quota: number; selected: number }>;
  paretoDiversityEnabled: boolean;
  entropyWeightEnabled: boolean;
  entropyWeight: number;
  paretoPoolMultiplier: number;
  distanceMode: DistanceMode;
  evolveproRound: number;
  roundSize: number;
  benchmarkTopPercentile: number;
  benchmarkRandomTrials: number;
  benchmarkRandomSeed: number | null;
  benchmarkRunning: boolean;
  showBenchmark: boolean;
  benchmarkResults: Record<string, BenchmarkResult> | null;
  autoRedesignOnLoad: boolean;
  saveCache: boolean;
  structureLoaded: boolean;
  structureLoading: boolean;
  poolVariants: string[];
  uniprotCandidates: UniprotCandidate[];
  uniprotSearching: boolean;

  // Actions
  setPipelineMode: (enabled: boolean) => void;
  setPositionDiversityEnabled: (enabled: boolean) => void;
  setMaxPerPosition: (n: number) => void;
  setDomainDiversityEnabled: (enabled: boolean) => void;
  setDomainStrategy: (strategy: "proportional" | "equal") => void;
  setDomainOverlapPolicy: (policy: DomainOverlapPolicy) => void;
  setLinkerHandling: (handling: LinkerHandling) => void;
  setDomainQuotaMin: (value: number) => void;
  fetchDomains: (accession: string, clearCandidates?: boolean) => Promise<void>;
  setDomains: (domains: DomainInfo[]) => void;
  toggleDomain: (domainKey: string) => void;
  setParetoDiversityEnabled: (enabled: boolean) => void;
  setEntropyWeightEnabled: (enabled: boolean) => void;
  setEntropyWeight: (weight: number) => void;
  setParetoPoolMultiplier: (value: number) => void;
  setDistanceMode: (mode: DistanceMode) => void;
  setEvolveproRound: (n: number) => void;
  setRoundSize: (n: number) => void;
  setBenchmarkTopPercentile: (value: number) => void;
  setBenchmarkRandomTrials: (value: number) => void;
  setBenchmarkRandomSeed: (seed: number | null) => void;
  runBenchmark: () => Promise<void>;
  setShowBenchmark: (show: boolean) => void;
  setAutoRedesignOnLoad: (enabled: boolean) => void;
  setSaveCache: (enabled: boolean) => void;
  searchUniprot: (geneName: string, organism: string, translation: string, knownAccession: string) => Promise<void>;
  fetchStructure: (accession: string) => Promise<void>;
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
        state.loadEvolveproCsv(state.evolveproCsvPath).catch((err) => console.warn("[diversity] CSV reload failed:", err));
      }
    }, 300);
  }

  return ({
  pipelineMode: true,
  positionDiversityEnabled: true,
  maxPerPosition: 1,
  domainDiversityEnabled: true,
  domainStrategy: "proportional",
  domainOverlapPolicy: "first",
  linkerHandling: "include",
  domainQuotaMin: 1,
  uniprotAccession: "",
  domains: [],
  domainLoading: false,
  disabledDomains: [] as string[],
  domainStats: {},
  paretoDiversityEnabled: true,
  entropyWeightEnabled: true,
  entropyWeight: 0.3,
  paretoPoolMultiplier: 2.0,
  distanceMode: "auto",
  evolveproRound: 1,
  roundSize: 96,
  benchmarkTopPercentile: 10,
  benchmarkRandomTrials: 100,
  benchmarkRandomSeed: null,
  benchmarkRunning: false,
  showBenchmark: false,
  benchmarkResults: null,
  autoRedesignOnLoad: true,
  saveCache: true,
  poolVariants: [] as string[],
  structureLoaded: false,
  structureLoading: false,
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

  setDomainOverlapPolicy: (policy: DomainOverlapPolicy) => {
    set({ domainOverlapPolicy: policy });
    debouncedReload();
  },

  setLinkerHandling: (handling: LinkerHandling) => {
    set({ linkerHandling: handling });
    debouncedReload();
  },

  setDomainQuotaMin: (value: number) => {
    set({ domainQuotaMin: Math.max(0, Math.min(20, Math.round(value))) });
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
      const { evolveproCsvPath, structureLoaded } = get();
      if (evolveproCsvPath && result.domains.length > 0) await get().loadEvolveproCsv(evolveproCsvPath);
      // Fetch AlphaFold structure for manual accession entry
      if (!structureLoaded) {
        get().fetchStructure(accession);
      }
    } catch (err) {
      set({ domainLoading: false, statusMessage: `Domain fetch failed: ${formatError(err)}` });
    }
  },

  setDomains: (domains: DomainInfo[]) => {
    set({ domains, disabledDomains: [] });
    const { evolveproCsvPath, domainDiversityEnabled } = get();
    if (evolveproCsvPath && domainDiversityEnabled) get().loadEvolveproCsv(evolveproCsvPath).catch((err) => console.warn("[diversity] CSV reload failed:", err));
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

  setEntropyWeight: (weight: number) => {
    const clamped = Math.max(0, Math.min(1, weight));
    set({ entropyWeight: clamped });
    debouncedReload();
  },

  setParetoPoolMultiplier: (value: number) => {
    const clamped = Math.max(1, Math.min(10, value));
    set({ paretoPoolMultiplier: clamped });
    debouncedReload();
  },

  setDistanceMode: (mode: DistanceMode) => {
    set({ distanceMode: mode });
    debouncedReload();
  },

  setEvolveproRound: (n: number) => {
    set({ evolveproRound: Math.max(1, Math.round(n)) });
    debouncedReload();
  },

  setRoundSize: (n: number) => {
    set({ roundSize: Math.max(1, Math.min(960, Math.round(n))) });
    debouncedReload();
  },

  setBenchmarkTopPercentile: (value: number) => {
    const clamped = Math.max(1, Math.min(100, value));
    set({ benchmarkTopPercentile: clamped });
  },

  setBenchmarkRandomTrials: (value: number) => {
    const clamped = Math.max(1, Math.min(1000, Math.round(value)));
    set({ benchmarkRandomTrials: clamped });
  },

  setBenchmarkRandomSeed: (seed: number | null) => {
    set({ benchmarkRandomSeed: seed });
  },

  runBenchmark: async () => {
    const state = get();
    const entries = Object.entries(state.yPredMap)
      .map(([variant, fitness]) => ({ variant, fitness }))
      .sort((a, b) => b.fitness - a.fitness);
    if (entries.length === 0) {
      set({ statusMessage: "Benchmark requires EVOLVEpro variants" });
      return;
    }

    const activeDomains = state.domains
      .filter((d) => !state.disabledDomains.includes(`${d.name}-${d.start}`))
      .map((d) => ({ name: d.name, start: d.start, end: d.end }));

    set({ benchmarkRunning: true, statusMessage: "Running benchmark..." });
    try {
      const result = await sendRequest<{ results: Record<string, BenchmarkResult> }>("run_benchmark", {
        landscape: entries,
        ground_truth: state.yPredMap,
        n_select: Math.max(1, state.maxPrimers),
        n_random_trials: state.benchmarkRandomTrials,
        top_percentile: state.benchmarkTopPercentile,
        domains: activeDomains,
        domain_strategy: state.domainStrategy,
        max_per_position: state.maxPerPosition,
        entropy_weight: state.entropyWeightEnabled ? state.entropyWeight : 0,
        pool_multiplier: state.paretoPoolMultiplier,
        distance_mode: state.distanceMode,
        random_seed: state.benchmarkRandomSeed,
      }, 120_000);
      set({
        benchmarkRunning: false,
        benchmarkResults: result.results,
        showBenchmark: true,
        statusMessage: "Benchmark complete",
      });
    } catch (err) {
      set({
        benchmarkRunning: false,
        statusMessage: `Benchmark failed: ${formatError(err)}`,
      });
    }
  },

  setShowBenchmark: (show: boolean) => set({ showBenchmark: show }),

  setAutoRedesignOnLoad: (enabled: boolean) => {
    set({ autoRedesignOnLoad: enabled });
  },

  setSaveCache: (enabled: boolean) => {
    set({ saveCache: enabled });
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
      // Auto-select top result
      const top = result.candidates[0];
      const acc = top?.accession ?? "";
      let statusMsg = "UniProt: no matching entries found";
      if (result.error_detail && result.candidates.length === 0) {
        statusMsg = `UniProt search error: ${result.error_detail}`;
      } else if (top) {
        statusMsg = `UniProt: auto-selected ${top.accession} (${top.identity.toFixed(1)}% identity)`;
      }
      set({
        uniprotCandidates: result.candidates,
        uniprotSearching: false,
        ...(acc && { uniprotAccession: acc }),
        statusMessage: statusMsg,
      });
      // Auto-trigger AlphaFold structure fetch
      if (acc) {
        get().fetchStructure(acc);
      }
    } catch (err) {
      set({ uniprotSearching: false, statusMessage: `UniProt search failed: ${formatError(err)}` });
    }
  },

  fetchStructure: async (accession: string) => {
    set({ structureLoading: true, statusMessage: "AlphaFold structure loading..." });
    try {
      const result = await sendRequest<StructureResult>("fetch_structure", { accession }, 30_000);
      if (result.success) {
        set({
          structureLoaded: true,
          structureLoading: false,
          statusMessage: `AlphaFold structure loaded: ${result.residues} Cα residues`,
        });
        // Re-trigger CSV selection with structure now available
        const { evolveproCsvPath } = get();
        if (evolveproCsvPath) await get().loadEvolveproCsv(evolveproCsvPath);
      } else {
        set({
          structureLoaded: false,
          structureLoading: false,
          statusMessage: `AlphaFold structure unavailable (using position distance) — ${result.error ?? "not in DB"}`,
        });
      }
    } catch (err) {
      set({
        structureLoaded: false,
        structureLoading: false,
        statusMessage: `AlphaFold fetch failed: ${formatError(err)}`,
      });
    }
  },

  cancelDiversityReload: () => {
    if (reloadTimer) { clearTimeout(reloadTimer); reloadTimer = null; }
  },
});
};
