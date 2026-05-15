import i18next from "i18next";
import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  DistanceMode,
  DomainOverlapPolicy,
  DomainInfo,
  LinkerHandling,
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
        statusMessage: `EVOLVEpro reload failed after ${reason}: ${formatError(err)}`,
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

  // NOTE: 호출자(searchUniprot)가 requireNetworkConsent 통과를 보장함.
  // 이 함수를 다른 곳에서 직접 호출할 경우 consent 가드를 별도로 추가할 것.
  async function enrichUniprotStructureFlags(searchGeneration: number, accessions: string[]) {
    if (accessions.length === 0) return;
    try {
      const result = await sendRequest(
        "check_structures_available",
        { accessions },
        20_000,
      );
      if (searchGeneration !== uniprotSearchGeneration) return;
      const current = get().uniprotCandidates;
      if (current.length === 0) return;
      set({
        uniprotCandidates: current.map((candidate) => (
          candidate.accession in result.availability
            ? { ...candidate, has_structure: result.availability[candidate.accession] }
            : candidate
        )),
      });
    } catch {
      // Best-effort badge enrichment only; keep primary search fast and resilient.
    }
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
  disabledDomains: [],
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
  poolVariants: [],
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
    const consentGranted = await get().requireNetworkConsent();
    if (!consentGranted) {
      const reason = get().offlineMode ? i18next.t("diversity.offlineReason") : i18next.t("diversity.consentReason");
      set({ statusMessage: i18next.t("diversity.domainFetchCancelled", { reason }) });
      return;
    }
    const requestedAccession = accession.trim();
    const fetchGeneration = ++domainFetchGeneration;
    uniprotSearchGeneration += 1;
    set({
      domainLoading: true,
      uniprotSearching: false,
      ...(clearCandidates && { uniprotCandidates: [] }),
      uniprotAccession: requestedAccession,
      structureLoaded: get().structureAccession === requestedAccession,
      ...(get().structureAccession !== requestedAccession && {
        structureLoading: false,
      }),
      statusMessage: "Fetching domain info...",
    });
    try {
      const result = await sendRequest(
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
        disabledDomains: [],
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
      const result = await sendRequest("run_benchmark", {
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
    const consentGranted = await get().requireNetworkConsent();
    if (!consentGranted) {
      const reason = get().offlineMode ? i18next.t("diversity.offlineReason") : i18next.t("diversity.consentReason");
      set({ statusMessage: i18next.t("diversity.uniprotSearchCancelled", { reason }) });
      return;
    }
    const searchGeneration = ++uniprotSearchGeneration;
    set({ uniprotSearching: true, statusMessage: "UniProt BLAST search in progress..." });
    try {
      // Backend BLAST polling waits up to 300s for EBI queue backlogs.
      // Keep the client timeout longer so successful long-running searches
      // are not rejected locally before the sidecar returns.
      const result = await sendRequest("search_uniprot", {
        gene_name: geneName,
        organism,
        translation,
        known_accession: knownAccession,
      }, 360_000);
      if (searchGeneration !== uniprotSearchGeneration) return;
      // Auto-fill only when backend confirms high-identity match (≥95%)
      const acc = result.auto_selected ?? "";
      const top = result.candidates[0];
      let statusMsg = "UniProt: no matching entries found";
      if (result.error_detail && result.candidates.length === 0) {
        statusMsg = `UniProt search error: ${result.error_detail}`;
      } else if (acc && top) {
        statusMsg = `UniProt: auto-matched ${acc} (${top.identity.toFixed(1)}% identity)`;
      } else if (result.candidates.length > 0) {
        statusMsg = `UniProt: ${result.candidates.length} candidate(s) found — select manually`;
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
      if (result.candidates.length > 0) {
        void enrichUniprotStructureFlags(
          searchGeneration,
          result.candidates.map((candidate) => candidate.accession),
        );
      }
      if (acc) {
        void get().fetchDomains(acc, false);
      }
    } catch (err) {
      if (searchGeneration !== uniprotSearchGeneration) return;
      set({ uniprotSearching: false, statusMessage: `UniProt search failed: ${formatError(err)}` });
    }
  },

  fetchStructure: async (accession: string) => {
    const consentGranted = await get().requireNetworkConsent();
    if (!consentGranted) {
      const reason = get().offlineMode ? i18next.t("diversity.offlineReason") : i18next.t("diversity.consentReason");
      set({ statusMessage: i18next.t("diversity.alphafoldFetchCancelled", { reason }) });
      return;
    }
    const requestedAccession = accession.trim();
    if (!requestedAccession) return;
    const fetchGeneration = ++structureFetchGeneration;
    set({
      structureLoading: true,
      structureLoaded: get().structureAccession === requestedAccession,
      statusMessage: "AlphaFold structure loading...",
    });
    try {
      const result = await sendRequest(
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
