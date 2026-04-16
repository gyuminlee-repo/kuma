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
  SearchUniprotResult,
  StructureResult,
} from "../../types/models";

import type { DiversitySlice } from "../slice-interfaces";
export type { DiversitySlice };

export const createDiversitySlice: StateCreator<AppState, [], [], DiversitySlice> = (set, get) => {
  let reloadTimer: ReturnType<typeof setTimeout> | null = null;
  let domainFetchGeneration = 0;
  let uniprotSearchGeneration = 0;
  let structureFetchGeneration = 0;

  async function reloadEvolveproCsv(reason: string) {
    const state = get();
    if (!state.evolveproCsvPath) return;
    try {
      await state.loadEvolveproCsv(state.evolveproCsvPath);
    } catch (err) {
      set({
        statusMessage: `${state.mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"} reload failed after ${reason}: ${formatError(err)}`,
      });
    }
  }

  function shouldReloadAfterStructureFetch(state: AppState) {
    return Boolean(
      state.evolveproCsvPath
      && state.paretoDiversityEnabled
      && state.distanceMode !== "1d",
    );
  }

  function debouncedReload() {
    if (reloadTimer) clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
      reloadTimer = null;
      void reloadEvolveproCsv("diversity settings change");
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
  structureAccession: "",
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
    const requestedAccession = accession.trim();
    const fetchGeneration = ++domainFetchGeneration;
    uniprotSearchGeneration += 1;
    set({
      domainLoading: true,
      ...(clearCandidates && { uniprotCandidates: [] }),
      uniprotAccession: requestedAccession,
      structureLoaded: get().structureAccession === requestedAccession,
      ...(get().structureAccession !== requestedAccession && {
        structureLoading: false,
      }),
      statusMessage: "Fetching domain info...",
    });
    try {
      const result = await sendRequest<FetchDomainsResult>(
        "fetch_domains",
        { accession: requestedAccession },
        120_000,
      );
      if (fetchGeneration !== domainFetchGeneration) return;
      const state = get();
      const structureMatches = state.structureAccession === requestedAccession;
      const deferReloadToStructureFetch = (
        requestedAccession !== ""
        && !structureMatches
        && shouldReloadAfterStructureFetch(state)
      );
      set({
        uniprotAccession: requestedAccession,
        domains: result.domains,
        disabledDomains: [] as string[],
        domainLoading: false,
        structureLoaded: structureMatches,
        ...(structureMatches ? {} : { structureLoading: false }),
        statusMessage: result.domains.length > 0
          ? `Domains: ${result.domains.length} found (${result.source})`
          : result.error_msg ? `Domain fetch failed: ${result.error_msg}` : "No domains found",
      });
      if (
        !deferReloadToStructureFetch
        && state.evolveproCsvPath
        && result.domains.length > 0
      ) {
        await get().loadEvolveproCsv(state.evolveproCsvPath);
      }
      if (requestedAccession && !structureMatches) {
        void get().fetchStructure(requestedAccession);
      }
    } catch (err) {
      if (fetchGeneration !== domainFetchGeneration) return;
      set({ domainLoading: false, statusMessage: `Domain fetch failed: ${formatError(err)}` });
    }
  },

  setDomains: (domains: DomainInfo[]) => {
    set({ domains, disabledDomains: [] });
    const { evolveproCsvPath, domainDiversityEnabled } = get();
    if (evolveproCsvPath && domainDiversityEnabled) {
      void reloadEvolveproCsv("manual domain update");
    }
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
        structure_accession: state.uniprotAccession || undefined,
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
    const searchGeneration = ++uniprotSearchGeneration;
    set({ uniprotSearching: true, statusMessage: "UniProt BLAST search in progress..." });
    try {
      const result = await sendRequest<SearchUniprotResult>("search_uniprot", {
        gene_name: geneName,
        organism,
        translation,
        known_accession: knownAccession,
      }, 120_000);
      if (searchGeneration !== uniprotSearchGeneration) return;
      // Auto-select top result
      const top = result.candidates[0];
      const acc = top?.accession ?? "";
      let statusMsg = "UniProt: no matching entries found";
      if (result.error_detail && result.candidates.length === 0) {
        statusMsg = `UniProt search error: ${result.error_detail}`;
      } else if (top) {
        statusMsg = `UniProt: auto-selected ${top.accession} (${top.identity.toFixed(1)}% identity)`;
      }
      const structureMatches = acc !== "" && get().structureAccession === acc;
      set({
        uniprotCandidates: result.candidates,
        uniprotSearching: false,
        uniprotAccession: acc,
        structureLoaded: structureMatches,
        structureLoading: false,
        statusMessage: statusMsg,
      });
      if (acc && !structureMatches) {
        void get().fetchStructure(acc);
      }
    } catch (err) {
      if (searchGeneration !== uniprotSearchGeneration) return;
      set({ uniprotSearching: false, statusMessage: `UniProt search failed: ${formatError(err)}` });
    }
  },

  fetchStructure: async (accession: string) => {
    const requestedAccession = accession.trim();
    if (!requestedAccession) return;
    const fetchGeneration = ++structureFetchGeneration;
    set({
      structureLoading: true,
      structureLoaded: get().structureAccession === requestedAccession,
      statusMessage: "AlphaFold structure loading...",
    });
    try {
      const result = await sendRequest<StructureResult>(
        "fetch_structure",
        { accession: requestedAccession },
        30_000,
      );
      if (
        fetchGeneration !== structureFetchGeneration
        || get().uniprotAccession !== requestedAccession
      ) {
        return;
      }
      if (result.success) {
        set({
          structureLoaded: true,
          structureLoading: false,
          structureAccession: requestedAccession,
          statusMessage: `AlphaFold structure loaded: ${result.residues} Cα residues`,
        });
        const state = get();
        if (shouldReloadAfterStructureFetch(state)) {
          await state.loadEvolveproCsv(state.evolveproCsvPath);
        }
      } else {
        set({
          structureLoaded: false,
          structureLoading: false,
          structureAccession: "",
          statusMessage: `AlphaFold structure unavailable (using position distance) — ${result.error ?? "not in DB"}`,
        });
        const state = get();
        if (shouldReloadAfterStructureFetch(state)) {
          await state.loadEvolveproCsv(state.evolveproCsvPath);
        }
      }
    } catch (err) {
      if (
        fetchGeneration !== structureFetchGeneration
        || get().uniprotAccession !== requestedAccession
      ) {
        return;
      }
      set({
        structureLoaded: false,
        structureLoading: false,
        structureAccession: "",
        statusMessage: `AlphaFold fetch failed: ${formatError(err)}`,
      });
    }
  },

  cancelDiversityReload: () => {
    if (reloadTimer) { clearTimeout(reloadTimer); reloadTimer = null; }
  },
});
};
