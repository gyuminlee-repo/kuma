import i18next from "i18next";
import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  ComputeDispersionResult,
  DistanceMode,
  DomainOverlapPolicy,
  DomainInfo,
  FetchActiveSiteResult,
  FetchPdbTextResult,
  PredictStructureEsmfoldResult,
  LinkerHandling,
} from "../../types/models";

import type { DiversitySlice } from "../slice-interfaces";
export type { DiversitySlice };

import { resolveSelectionDomains } from "./inputSlice.helpers";
export const createDiversitySlice: StateCreator<AppState, [], [], DiversitySlice> = (set, get) => {
  let reloadTimer: ReturnType<typeof setTimeout> | null = null;
  let domainFetchGeneration = 0;
  let uniprotSearchGeneration = 0;
  let structureFetchGeneration = 0;
  let refDomainGeneration = 0;

  /** Per-accession PDB text cache — avoids redundant network fetches within a session. */
  const pdbTextCache = new Map<string, Promise<FetchPdbTextResult | null>>();
  /** Per-sequence ESMFold prediction cache — avoids redundant folds within a session. */
  const esmfoldCache = new Map<string, Promise<PredictStructureEsmfoldResult | null>>();


  function getActiveEvolveproPath(state: AppState): string {
    return state.evolveproCsvPath;
  }

  async function reloadEvolveproCsv(reason: string) {
    const state = get();
    const activePath = getActiveEvolveproPath(state);
    if (!activePath) return;
    try {
      await state.loadEvolveproCsv(activePath);
    } catch (err) {
      set({
        statusMessage: `EVOLVEpro reload failed after ${reason}: ${formatError(err)}`,
      });
    }
  }

  function shouldReloadAfterStructureFetch(state: AppState) {
    return Boolean(
      getActiveEvolveproPath(state)
      && (
        // Structural diversity always consumes 3D Cα coords when available, so
        // it must reload once the AlphaFold structure is cached, regardless of
        // distanceMode (which only gates the pareto 1D/3D distance path).
        state.structuralDiversityEnabled
        || (state.paretoDiversityEnabled && state.distanceMode !== "1d")
      ),
    );
  }

  function debouncedReload() {
    if (reloadTimer) clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
      reloadTimer = null;
      void reloadEvolveproCsv("diversity settings change");
    }, 300);
  }

  // If a Top-N-only session skipped the initial BLAST-backed UniProt
  // auto-search (see sequenceSlice.ts diversityConsumersEnabled gate),
  // uniprotAccession stays empty. Backfill it once the user later enables an
  // accession consumer (domain/pareto/structural diversity), so domain fetch
  // and the 3D view aren't silently empty.
  function maybeBackfillUniprotSearch() {
    const state = get();
    if (state.uniprotAccession || state.uniprotSearching) return;
    const seqInfo = state.seqInfo;
    const gene = seqInfo?.genes.find((g) => String(g.cds_start) === state.selectedGene) ?? seqInfo?.genes[0];
    const translation = gene?.translation ?? "";
    if (!gene || !translation) return;
    void state.searchUniprot(gene.gene, gene.organism ?? state.organism, translation, gene.uniprot_accession ?? "");
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
  structure3dState: "off",
  uniprotCandidates: [],
  uniprotSearching: false,
  structuralDiversityEnabled: false,
  structuralKappa: 0.3,
  refDomains: [],
  refDomainsLoading: false,
  refDomainHash: "",



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
    if (enabled) maybeBackfillUniprotSearch();
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
        && getActiveEvolveproPath(state)
        && result.domains.length > 0
      ) {
        await get().loadEvolveproCsv(getActiveEvolveproPath(state));
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
    set({ refDomains: domains, refDomainHash: "manual", disabledDomains: [] });
    const state = get();
    if (getActiveEvolveproPath(state) && state.domainDiversityEnabled) {
      void reloadEvolveproCsv("manual reference-domain update");
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
    if (enabled) maybeBackfillUniprotSearch();
  },
  setStructuralDiversityEnabled: (enabled: boolean) => {
    set({ structuralDiversityEnabled: enabled });
    debouncedReload();
    if (enabled) maybeBackfillUniprotSearch();
  },

  setStructuralKappa: (v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    set({ structuralKappa: clamped });
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

    const selectionDomains = resolveSelectionDomains(state.refDomains);
    const activeDomains = selectionDomains
      .filter((d) => !state.disabledDomains.includes(`${d.name}-${d.start}`))
      .map((d) => ({ name: d.name, start: d.start, end: d.end }));

    // Reference sequence for the backend frame guard, same source as
    // load_evolvepro: the selected gene's translation. Without it the guard
    // cannot verify a loaded structure covers the CDS frame.
    const benchGene =
      state.seqInfo?.genes.find((g) => String(g.cds_start) === state.selectedGene)
      ?? state.seqInfo?.genes[0];
    const benchRefSeq = benchGene?.translation ?? "";

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
        // A user-loaded structure file lives in structureAccession, not
        // uniprotAccession, so it must win here too (matches load_evolvepro).
        structure_accession: state.structureAccession || state.uniprotAccession || undefined,
        ref_seq: benchRefSeq,
        random_seed: state.benchmarkRandomSeed,
      }, 120_000);
      // Surface the same 3D-to-1D fallback notice load_evolvepro shows, so a
      // frame mismatch is not silent in the benchmark path either.
      const benchMismatch = result.structure_frame_mismatch
        ? ` | ${i18next.t("inputSlice.structureFrameMismatch")}`
        : "";
      set({
        benchmarkRunning: false,
        benchmarkResults: result.results,
        showBenchmark: true,
        statusMessage: `Benchmark complete${benchMismatch}`,
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
          await state.loadEvolveproCsv(getActiveEvolveproPath(state));
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
          await state.loadEvolveproCsv(getActiveEvolveproPath(state));
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

  loadStructureFile: async (filepath: string) => {
    const path = filepath.trim();
    if (!path) return;
    // A local file needs no network consent and has no accession to match, so
    // the fetchStructure guards do not apply. A generation counter still
    // discards a stale load if another begins first.
    const fetchGeneration = ++structureFetchGeneration;
    set({
      structureLoading: true,
      structureLoaded: false,
      statusMessage: i18next.t("diversity.structureFileLoading"),
    });
    try {
      const result = await sendRequest("load_structure_file", { filepath: path }, 60_000);
      if (fetchGeneration !== structureFetchGeneration) return;
      if (result.success && result.accession) {
        const picked =
          result.selection_metric === "ranking_score" || result.selection_metric === "mean_plddt"
            ? i18next.t("diversity.structureFileChosen", {
                source: result.source_name ?? "",
                count: result.candidates?.length ?? 0,
                metric: result.selection_metric,
              })
            : "";
        set({
          structureLoaded: true,
          structureLoading: false,
          structureAccession: result.accession,
          statusMessage: i18next.t("diversity.structureFileLoaded", {
            residues: result.residues ?? 0,
            picked,
          }),
        });
        const state = get();
        if (shouldReloadAfterStructureFetch(state)) {
          await state.loadEvolveproCsv(getActiveEvolveproPath(state));
        }
      } else {
        set({
          structureLoaded: false,
          structureLoading: false,
          structureAccession: "",
          statusMessage: i18next.t("diversity.structureFileFailed", {
            error: result.error ?? "unreadable",
          }),
        });
      }
    } catch (err) {
      if (fetchGeneration !== structureFetchGeneration) return;
      set({
        structureLoaded: false,
        structureLoading: false,
        structureAccession: "",
        statusMessage: i18next.t("diversity.structureFileFailed", { error: formatError(err) }),
      });
    }
  },

  fetchPdbText: async (accession: string): Promise<FetchPdbTextResult | null> => {
    const key = accession.trim();
    if (!key) return null;
    const cached = pdbTextCache.get(key);
    if (cached !== undefined) return cached;
    const promise = (async () => {
      const consentGranted = await get().requireNetworkConsent();
      if (!consentGranted) {
        const reason = get().offlineMode
          ? i18next.t("diversity.offlineReason")
          : i18next.t("diversity.consentReason");
        set({ statusMessage: reason });
        pdbTextCache.delete(key);
        return null;
      }
      try {
        const result = await sendRequest("fetch_pdb_text", { accession: key }, 30_000);
        return result;
      } catch (err) {
        pdbTextCache.delete(key);
        set({ statusMessage: `PDB text fetch failed: ${formatError(err)}` });
        return null;
      }
    })();
    pdbTextCache.set(key, promise);
    return promise;
  },

  predictStructureEsmfold: async (sequence: string): Promise<PredictStructureEsmfoldResult | null> => {
    const clean = sequence.trim();
    if (!clean) return null;
    const cached = esmfoldCache.get(clean);
    if (cached !== undefined) return cached;
    const promise = (async () => {
      const consentGranted = await get().requireNetworkConsent();
      if (!consentGranted) {
        const reason = get().offlineMode
          ? i18next.t("diversity.offlineReason")
          : i18next.t("diversity.consentReason");
        set({ statusMessage: i18next.t("diversity.esmfoldCancelled", { reason }) });
        esmfoldCache.delete(clean);
        return null;
      }
      set({ statusMessage: i18next.t("diversity.esmfoldPredicting") });
      try {
        const result = await sendRequest("predict_structure_esmfold", { sequence: clean }, 180_000);
        if (result.source === "error") {
          esmfoldCache.delete(clean);
          set({
            statusMessage: i18next.t("diversity.esmfoldFailed", {
              error: result.error_msg ?? i18next.t("statusBar.networkError"),
            }),
          });
          return result;
        }
        set({
          statusMessage: i18next.t("diversity.esmfoldDone", {
            residues: result.residue_count,
            plddt: result.plddt_mean.toFixed(1),
          }),
        });
        return result;
      } catch (err) {
        esmfoldCache.delete(clean);
        set({ statusMessage: i18next.t("diversity.esmfoldFailed", { error: formatError(err) }) });
        return null;
      }
    })();
    esmfoldCache.set(clean, promise);
    return promise;
  },

  fetchActiveSite: async (accession: string): Promise<FetchActiveSiteResult | null> => {
    const consentGranted = await get().requireNetworkConsent();
    if (!consentGranted) {
      const reason = get().offlineMode
        ? i18next.t("diversity.offlineReason")
        : i18next.t("diversity.consentReason");
      set({ statusMessage: reason });
      return null;
    }
    try {
      const result = await sendRequest(
        "fetch_active_site_residues",
        { accession: accession.trim() },
        30_000,
      );
      return result;
    } catch (err) {
      set({ statusMessage: `Active site fetch failed: ${formatError(err)}` });
      return null;
    }
  },

  computeDispersion: async ({
    accession,
    refSeq,
    positions,
    nTrials,
    seed,
    pdbText,
    coordinateFrame,
  }: {
    accession: string;
    refSeq: string;
    positions: number[];
    nTrials?: number;
    seed?: number | null;
    pdbText?: string | null;
    coordinateFrame?: "accession" | "reference";
  }): Promise<ComputeDispersionResult | null> => {
    const consentGranted = await get().requireNetworkConsent();
    if (!consentGranted) {
      const reason = get().offlineMode
        ? i18next.t("diversity.offlineReason")
        : i18next.t("diversity.consentReason");
      set({ statusMessage: reason });
      return null;
    }
    try {
      const params: {
        accession: string;
        ref_seq: string;
        positions: number[];
        n_trials?: number;
        seed?: number | null;
        pdb_text?: string | null;
        coordinate_frame?: "accession" | "reference";
      } = { accession: accession.trim(), ref_seq: refSeq, positions };
      if (nTrials !== undefined) params.n_trials = nTrials;
      if (seed !== undefined) params.seed = seed;
      if (pdbText !== undefined) params.pdb_text = pdbText;
      if (coordinateFrame !== undefined) params.coordinate_frame = coordinateFrame;
      const result = await sendRequest("compute_dispersion", params, 30_000);
      return result;
    } catch (err) {
      set({ statusMessage: `Dispersion compute failed: ${formatError(err)}` });
      return null;
    }
  },

  cancelDiversityReload: () => {
    if (reloadTimer) { clearTimeout(reloadTimer); reloadTimer = null; }
  },

  annotateReferenceDomains: async () => {
    const consentGranted = await get().requireNetworkConsent();
    if (!consentGranted) {
      const reason = get().offlineMode
        ? i18next.t("diversity.offlineReason")
        : i18next.t("diversity.consentReason");
      set({ statusMessage: i18next.t("diversity.sequenceDomainScanCancelled", { reason }) });
      return;
    }
    const state = get();
    const seqInfo = state.seqInfo;
    if (!seqInfo?.genes.length) return;
    const gene =
      seqInfo.genes.find((g) => String(g.cds_start) === state.selectedGene)
      ?? seqInfo.genes[0];
    const translation = gene?.translation;
    if (!translation) return;
    const generation = ++refDomainGeneration;
    set({
      refDomainsLoading: true,
      statusMessage: i18next.t("diversity.sequenceDomainScanning"),
    });
    try {
      const result = await sendRequest(
        "annotate_domains_by_sequence",
        { sequence: translation },
        660_000,
      );
      if (generation !== refDomainGeneration) return;
      // Stale guard: discard result if selected gene translation changed while request was in flight.
      const nowState = get();
      const nowSeqInfo = nowState.seqInfo;
      if (!nowSeqInfo) {
        set({ refDomainsLoading: false });
        return;
      }
      const nowGene =
        nowSeqInfo.genes.find((g) => String(g.cds_start) === nowState.selectedGene)
        ?? nowSeqInfo.genes[0];
      if (nowGene?.translation !== translation) {
        set({ refDomainsLoading: false });
        return;
      }
      if (result.source === "error") {
        set({
          refDomainsLoading: false,
          statusMessage: i18next.t("diversity.sequenceDomainScanFailed", {
            error: result.error_msg ?? i18next.t("statusBar.networkError"),
          }),
        });
        return;
      }
      const cacheSuffix = result.cache_hit ? i18next.t("diversity.sequenceDomainsCachedSuffix") : "";
      const statusMsg = result.domains.length > 0
        ? i18next.t("diversity.sequenceDomainsFound", { count: result.domains.length, cache: cacheSuffix })
        : i18next.t("diversity.sequenceDomainsNone");
      set({
        refDomains: result.domains,
        refDomainHash: result.ref_hash,
        refDomainsLoading: false,
        disabledDomains: [],
        statusMessage: statusMsg,
      });
      const refreshedState = get();
      if (
        result.domains.length > 0
        && getActiveEvolveproPath(refreshedState)
        && refreshedState.domainDiversityEnabled
      ) {
        await reloadEvolveproCsv("reference-domain annotation");
      }
    } catch (err) {
      if (generation !== refDomainGeneration) return;
      set({
        refDomainsLoading: false,
        statusMessage: i18next.t("diversity.sequenceDomainScanFailed", { error: formatError(err) }),
      });
    }
  },
});
};
