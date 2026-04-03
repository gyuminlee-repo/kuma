import type { StateCreator } from "zustand";
import type { SortingState, Updater } from "@tanstack/react-table";
import { sendRequest } from "../../lib/ipc";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  PlateMapping,
  PlateMapResult,
  SequenceInfo,
  WorkspaceData,
  WorkspaceV1,
  WorkspaceV2,
} from "../../types/models";

export interface ExportSlice {
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  progress: number;
  statusMessage: string;
  tableSorting: SortingState;
  getPlateMap: () => Promise<void>;
  exportExcel: (filepath: string) => Promise<void>;
  setTableSorting: (updater: Updater<SortingState>) => void;
  setStatus: (msg: string) => void;
  getWorkspaceSnapshot: () => WorkspaceV2;
  restoreWorkspace: (ws: WorkspaceData) => Promise<void>;
  resetAll: () => void;
}

function normalizeWorkspace(ws: WorkspaceData): WorkspaceV2 {
  if (ws.version === 2) {
    return ws;
  }

  const legacy = ws as WorkspaceV1;
  return {
    version: 2,
    inputs: {
      fastaPath: legacy.fastaPath,
      mutationInputMode: legacy.mutationInputMode,
      mutationText: legacy.mutationText,
      evolveproCsvPath: legacy.evolveproCsvPath,
      selectedGene: legacy.selectedGene,
    },
    settings: {
      codonStrategy: legacy.codonStrategy,
      maxPrimers: legacy.maxPrimers,
      tmFwdTarget: legacy.tmFwdTarget,
      tmRevTarget: legacy.tmRevTarget,
      tmOverlapTarget: legacy.tmOverlapTarget,
      gcMin: legacy.gcMin,
      gcMax: legacy.gcMax,
      primerLenEnabled: legacy.primerLenEnabled,
      fwdLenMin: legacy.fwdLenMin,
      fwdLenMax: legacy.fwdLenMax,
      revLenMin: legacy.revLenMin,
      revLenMax: legacy.revLenMax,
      fillOnFailure: legacy.fillOnFailure,
      uniprotAccession: legacy.uniprotAccession,
      domains: legacy.domains,
      domainDiversityEnabled: legacy.domainDiversityEnabled,
      domainStrategy: legacy.domainStrategy,
      domainOverlapPolicy: "first",
      linkerHandling: "include",
      domainQuotaMin: 1,
      paretoDiversityEnabled: legacy.paretoDiversityEnabled,
      disabledDomains: legacy.disabledDomains,
      rescuedMutations: legacy.rescuedMutations,
      entropyWeightEnabled: legacy.entropyWeightEnabled,
      entropyWeight: legacy.entropyWeight,
      paretoPoolMultiplier: 2.0,
      distanceMode: "auto",
      benchmarkTopPercentile: 10,
      benchmarkRandomTrials: 100,
      benchmarkRandomSeed: null,
      autoRedesignOnLoad: true,
      saveCache: true,
      organism: legacy.organism,
      pipelineMode: legacy.pipelineMode,
      positionDiversityEnabled: legacy.positionDiversityEnabled,
      maxPerPosition: legacy.maxPerPosition,
    },
    results: {
      designResults: legacy.designResults,
      successCount: legacy.successCount,
      totalCount: legacy.totalCount,
      failedMutations: legacy.failedMutations,
      plateMappings: legacy.plateMappings,
      dedupInfo: legacy.dedupInfo,
      manuallySwapped: legacy.manuallySwapped,
      customCandidates: legacy.customCandidates,
    },
    ui: {
      tableSorting: legacy.tableSorting,
    },
    cache: {
      evolveproTotalCount: legacy.evolveproTotalCount,
      evolveproFilteredCount: legacy.evolveproFilteredCount,
      evolveproParetoExchanges: legacy.evolveproParetoExchanges,
      evolveproStepStats: legacy.evolveproStepStats,
      benchmarkResults: null,
    },
  };
}

export const createExportSlice: StateCreator<AppState, [], [], ExportSlice> = (set, get) => ({
  plateMappings: [],
  dedupInfo: {},
  progress: 0,
  statusMessage: "Ready",
  tableSorting: [] as SortingState,

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

  exportExcel: async (filepath: string) => {
    try {
      const { designResults, plateMappings, dedupInfo, tableSorting } = get();
      const sortedMuts = getSortedMutations(designResults, tableSorting);
      const ordered = reorderMappings(plateMappings, dedupInfo, sortedMuts);

      const resultByMut = new Map(designResults.map((r) => [r.mutation, r]));
      const enriched = ordered.map((m) => {
        const r = resultByMut.get(m.mutation);
        if (!r) return m;
        return {
          ...m,
          tm: m.primer_type === "forward" ? r.tm_no_fwd : r.tm_no_rev,
          tm_overlap: r.tm_overlap,
          wt_codon: r.wt_codon,
          mt_codon: r.mt_codon,
        };
      });

      await sendRequest("export_excel", { filepath, mappings: enriched, dedup_info: dedupInfo });
      set({ statusMessage: `Exported Excel: ${filepath}` });
    } catch (err) {
      set({ statusMessage: `Excel export failed: ${formatError(err)}` });
    }
  },

  setTableSorting: (updater: Updater<SortingState>) => {
    const current = get().tableSorting;
    const next = typeof updater === "function" ? updater(current) : updater;
    set({ tableSorting: next });
  },

  setStatus: (msg: string) => set({ statusMessage: msg }),

  getWorkspaceSnapshot: () => {
    const s = get();
    return {
      version: 2 as const,
      inputs: {
        fastaPath: s.fastaPath,
        mutationInputMode: s.mutationInputMode,
        mutationText: s.mutationText,
        evolveproCsvPath: s.evolveproCsvPath,
        selectedGene: s.selectedGene,
      },
      settings: {
        codonStrategy: s.codonStrategy,
        maxPrimers: s.maxPrimers,
        tmFwdTarget: s.tmFwdTarget,
        tmRevTarget: s.tmRevTarget,
        tmOverlapTarget: s.tmOverlapTarget,
        gcMin: s.gcMin,
        gcMax: s.gcMax,
        primerLenEnabled: s.primerLenEnabled,
        fwdLenMin: s.fwdLenMin,
        fwdLenMax: s.fwdLenMax,
        revLenMin: s.revLenMin,
        revLenMax: s.revLenMax,
        fillOnFailure: s.fillOnFailure,
        uniprotAccession: s.uniprotAccession || undefined,
        domains: s.domains.length > 0 ? s.domains : undefined,
        domainDiversityEnabled: s.domainDiversityEnabled || undefined,
        domainStrategy: s.domainDiversityEnabled ? s.domainStrategy : undefined,
        domainOverlapPolicy: s.domainDiversityEnabled ? s.domainOverlapPolicy : undefined,
        linkerHandling: s.domainDiversityEnabled ? s.linkerHandling : undefined,
        domainQuotaMin: s.domainDiversityEnabled ? s.domainQuotaMin : undefined,
        paretoDiversityEnabled: s.paretoDiversityEnabled || undefined,
        disabledDomains: s.disabledDomains,
        rescuedMutations: s.rescuedMutations,
        entropyWeightEnabled: s.entropyWeightEnabled,
        entropyWeight: s.entropyWeight,
        paretoPoolMultiplier: s.paretoPoolMultiplier,
        distanceMode: s.distanceMode,
        benchmarkTopPercentile: s.benchmarkTopPercentile,
        benchmarkRandomTrials: s.benchmarkRandomTrials,
        benchmarkRandomSeed: s.benchmarkRandomSeed,
        autoRedesignOnLoad: s.autoRedesignOnLoad,
        saveCache: s.saveCache,
        organism: s.organism,
        pipelineMode: s.pipelineMode,
        positionDiversityEnabled: s.positionDiversityEnabled,
        maxPerPosition: s.maxPerPosition,
        evolveproRound: s.evolveproRound,
        roundSize: s.roundSize,
      },
      results: {
        designResults: s.designResults,
        successCount: s.successCount,
        totalCount: s.totalCount,
        failedMutations: s.failedMutations,
        plateMappings: s.plateMappings,
        dedupInfo: s.dedupInfo,
        manuallySwapped: s.manuallySwapped,
        customCandidates: s.customCandidates,
      },
      ui: {
        tableSorting: s.tableSorting,
      },
      ...(s.saveCache && {
        cache: {
          evolveproTotalCount: s.evolveproTotalCount,
          evolveproFilteredCount: s.evolveproFilteredCount,
          evolveproParetoExchanges: s.evolveproParetoExchanges,
          evolveproStepStats: s.evolveproStepStats,
          benchmarkResults: s.benchmarkResults,
        },
      }),
    };
  },

  restoreWorkspace: async (ws: WorkspaceData) => {
    const normalized = normalizeWorkspace(ws);
    const { inputs, settings, results, ui, cache } = normalized;
    const store = get();
    store.resetAll();
    set({
      mutationInputMode: inputs.mutationInputMode ?? "text",
      mutationText: inputs.mutationText ?? "",
      evolveproCsvPath: inputs.evolveproCsvPath ?? "",
      codonStrategy: settings.codonStrategy ?? "closest",
      maxPrimers: settings.maxPrimers ?? 95,
    });
    if (inputs.fastaPath) {
      const info = await sendRequest<SequenceInfo>("load_fasta", { filepath: inputs.fastaPath });
      set({ fastaPath: inputs.fastaPath, seqInfo: info });
      if (inputs.selectedGene) {
        const geneExists = info?.genes.some((g) => String(g.cds_start) === String(inputs.selectedGene));
        if (geneExists) set({ selectedGene: inputs.selectedGene });
      }
    }
    set({
      designResults: results.designResults ?? [],
      successCount: results.successCount ?? 0,
      totalCount: results.totalCount ?? 0,
      failedMutations: results.failedMutations ?? [],
      plateMappings: results.plateMappings ?? [],
      dedupInfo: results.dedupInfo ?? {},
      tableSorting: (ui.tableSorting ?? []) as SortingState,
      manuallySwapped: (() => {
        const rawSwapped = results.manuallySwapped ?? {};
        const safe: Record<string, "fwd" | "rev" | "both"> = {};
        for (const [k, v] of Object.entries(rawSwapped)) {
          if (v === "fwd" || v === "rev" || v === "both") safe[k] = v;
        }
        return safe;
      })(),
      customCandidates: results.customCandidates ?? {},
      tmFwdTarget: settings.tmFwdTarget ?? 62,
      tmRevTarget: settings.tmRevTarget ?? 58,
      tmOverlapTarget: settings.tmOverlapTarget ?? 42,
      gcMin: settings.gcMin ?? 40,
      gcMax: settings.gcMax ?? 60,
      primerLenEnabled: settings.primerLenEnabled ?? false,
      fwdLenMin: settings.fwdLenMin ?? 18,
      fwdLenMax: settings.fwdLenMax ?? 45,
      revLenMin: settings.revLenMin ?? 18,
      revLenMax: settings.revLenMax ?? 30,
      fillOnFailure: settings.fillOnFailure ?? false,
      uniprotAccession: settings.uniprotAccession ?? "",
      domains: settings.domains ?? [],
      ...(settings.disabledDomains && { disabledDomains: settings.disabledDomains }),
      rescuedMutations: settings.rescuedMutations ?? [],
      domainOverlapPolicy: settings.domainOverlapPolicy ?? "first",
      linkerHandling: settings.linkerHandling ?? "include",
      domainQuotaMin: settings.domainQuotaMin ?? 1,
      entropyWeightEnabled: settings.entropyWeightEnabled ?? true,
      entropyWeight: settings.entropyWeight ?? 0.3,
      paretoPoolMultiplier: settings.paretoPoolMultiplier ?? 2.0,
      distanceMode: settings.distanceMode ?? "auto",
      benchmarkTopPercentile: settings.benchmarkTopPercentile ?? 10,
      benchmarkRandomTrials: settings.benchmarkRandomTrials ?? 100,
      benchmarkRandomSeed: settings.benchmarkRandomSeed ?? null,
      autoRedesignOnLoad: settings.autoRedesignOnLoad ?? true,
      saveCache: settings.saveCache ?? true,
      ...(settings.organism && { organism: settings.organism }),
      pipelineMode: settings.pipelineMode ?? true,
      positionDiversityEnabled: settings.positionDiversityEnabled ?? true,
      maxPerPosition: settings.maxPerPosition ?? 1,
      evolveproRound: settings.evolveproRound ?? 1,
      roundSize: settings.roundSize ?? 96,
      evolveproTotalCount: cache?.evolveproTotalCount ?? 0,
      evolveproFilteredCount: cache?.evolveproFilteredCount ?? null,
      evolveproParetoExchanges: cache?.evolveproParetoExchanges ?? null,
      evolveproStepStats: cache?.evolveproStepStats ?? null,
      benchmarkResults: cache?.benchmarkResults ?? null,
      domainDiversityEnabled: settings.domainDiversityEnabled ?? true,
      domainStrategy: settings.domainStrategy ?? "proportional",
      paretoDiversityEnabled: settings.paretoDiversityEnabled ?? true,
      statusMessage: (settings.autoRedesignOnLoad ?? true)
        ? "Workspace loaded. Re-designing to sync backend..."
        : "Workspace loaded.",
    });
    if ((settings.autoRedesignOnLoad ?? true) && inputs.mutationText && inputs.fastaPath) {
      await get().designPrimers();
    }
  },

  resetAll: () => {
    set({
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
      parsedMutations: [],
      parseErrors: [],
      selectedGene: "",
      uniprotCandidates: [],
      uniprotSearching: false,
      isDesigning: false,
      designResults: [],
      successCount: 0,
      totalCount: 0,
      failedMutations: [],
      codonStrategy: "closest",
      maxPrimers: 95,
      tmFwdTarget: 62,
      tmRevTarget: 58,
      tmOverlapTarget: 42,
      gcMin: 40,
      gcMax: 60,
      primerLenEnabled: false,
      fwdLenMin: 18,
      fwdLenMax: 45,
      revLenMin: 18,
      revLenMax: 30,
      fillOnFailure: false,
      manuallySwapped: {},
      customCandidates: {},
      rescuedMutations: [],
      structureLoaded: false,
      structureLoading: false,
      evolveproTotalCount: 0,
      evolveproFilteredCount: null,
      evolveproParetoExchanges: null,
      evolveproStepStats: null,
      showReport: false,
      organism: "ecoli",
      plateMappings: [],
      dedupInfo: {},
      progress: 0,
      statusMessage: "Ready",
      tableSorting: [],
    });
  },
});
