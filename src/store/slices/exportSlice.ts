import i18next from "i18next";
import type { StateCreator } from "zustand";
import type { SortingState, Updater } from "@tanstack/react-table";
import { sendRequest } from "../../lib/ipc-kuro";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import { notifyJobDone, notifyJobError } from "../../lib/toast";
import type { AppState } from "../types";
import type {
  BenchmarkResult,
  SequenceInfo,
  WorkspaceData,
  WorkspaceV1,
  WorkspaceV2,
  WorkspaceV3,
} from "../../types/models";
import { useRoundStore } from "../round/roundSlice";

import type { ExportSlice } from "../slice-interfaces";
export type { ExportSlice };

function normalizeWorkspace(ws: WorkspaceV1 | WorkspaceV2): WorkspaceV2 {
  if (ws.version === 2) {
    return ws;
  }

  const legacy: WorkspaceV1 = ws;
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
      selectedPolymerase: undefined,
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
      overlapMode: undefined,
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
      rescuedMutationDetails: [],
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

function avg(values: number[]): number {
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function std(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = avg(values);
  return Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1));
}

function formatDomainAllocation(
  enabled: boolean,
  domains: Array<{ name: string }>,
  domainStats: Record<string, { quota: number; selected: number }>,
  domainStrategy: "proportional" | "equal",
): string {
  if (!enabled || domains.length === 0) return "OFF";
  const total = Object.values(domainStats).reduce((sum, stat) => sum + stat.selected, 0);
  const quota = Object.values(domainStats).reduce((sum, stat) => sum + stat.quota, 0);
  return quota > 0 ? `${domainStrategy}: ${total}/${quota}` : `${domainStrategy} (${domains.length} domains)`;
}

function buildReportData(state: AppState) {
  const successCount = state.designResults.length;
  const failCount = state.failedMutations.length;
  const totalCount = state.totalCount;
  const tmMet = state.designResults.filter((r) => r.tm_condition_met).length;
  const fwdTms = state.designResults.map((r) => r.tm_no_fwd).filter((t) => t > 0);
  const revTms = state.designResults.map((r) => r.tm_no_rev).filter((t) => t > 0);
  const ovTms = state.designResults.map((r) => r.tm_overlap).filter((t) => t > 0);
  const positionRemoved = state.evolveproStepStats?.position_filter_removed ?? state.evolveproFilteredCount;
  const domainSelected = state.evolveproStepStats?.domain_selected;
  const paretoExchanges = state.evolveproStepStats?.pareto_exchanges ?? state.evolveproParetoExchanges;
  const rescueTotal = state.rescueStats.pool_cascade + state.rescueStats.auto_relax;
  const rescuePenalties = state.rescuedMutationDetails
    .map((r) => r.penalty)
    .filter((penalty): penalty is number => penalty != null);
  const rescuedSet = new Set(state.rescuedMutationDetails.map((detail) => detail.rescued_by));
  const avgRescuePenalty = avg(rescuePenalties);
  const avgNormalPenalty = avg(
    state.designResults.filter((r) => !rescuedSet.has(r.mutation)).map((r) => r.penalty),
  );

  const sections: Array<{ title: string; items: Array<{ label: string; value: string | number; warn?: boolean }> }> = [];

  if (state.pipelineMode) {
    sections.push({
      title: "Pipeline",
      items: [
        {
          label: "Step 1 filter",
          value: state.positionDiversityEnabled
            ? `max ${state.maxPerPosition}/pos${positionRemoved != null && positionRemoved > 0 ? ` (-${positionRemoved})` : ""}`
            : "OFF",
        },
        {
          label: "Step 2 domains",
          value: formatDomainAllocation(
            state.domainDiversityEnabled,
            state.domains,
            state.domainStats,
            state.domainStrategy,
          ),
        },
        { label: "Step 2 overlap", value: state.domainDiversityEnabled ? (state.domainOverlapPolicy === "largest" ? "LARGEST" : "FIRST") : "N/A" },
        { label: "Step 2 linker", value: state.domainDiversityEnabled ? state.linkerHandling.toUpperCase() : "N/A" },
        { label: "Step 2 min quota", value: state.domainDiversityEnabled ? state.domainQuotaMin : "N/A" },
        {
          label: "Step 3 Pareto",
          value: state.paretoDiversityEnabled
            ? `ON${paretoExchanges != null && paretoExchanges > 0 ? ` (${paretoExchanges} swapped)` : ""}`
            : "OFF",
        },
        {
          label: "Distance mode",
          value: state.distanceMode === "auto"
            ? (state.structureLoaded ? "AUTO -> 3D" : "AUTO -> 1D")
            : state.distanceMode.toUpperCase(),
        },
        { label: "Pareto pool", value: `${state.paretoPoolMultiplier.toFixed(2)}x` },
        { label: "Entropy-guided", value: state.entropyWeightEnabled ? `ON (${state.entropyWeight.toFixed(2)})` : "OFF" },
        { label: "AlphaFold 3D", value: state.structureLoaded ? "ON (Cα distance)" : "OFF (1D distance)" },
        ...(positionRemoved != null && state.positionDiversityEnabled ? [{ label: "Removed by Step 1", value: positionRemoved }] : []),
        ...(domainSelected != null && state.domainDiversityEnabled ? [{ label: "After Step 2", value: domainSelected }] : []),
        ...(paretoExchanges != null && state.paretoDiversityEnabled ? [{ label: "Step 3 exchanges", value: paretoExchanges }] : []),
        ...(state.evolveproTotalCount > 0 ? [{
          label: state.mutationInputMode === "multi-evolve" ? "MULTI-evolve pool" : "EVOLVEpro pool",
          value: `${state.evolveproTotalCount} variants`,
        }] : []),
      ],
    });
  }

  sections.push({
    title: "Benchmark Defaults",
    items: [
      { label: "Top percentile", value: `${state.benchmarkTopPercentile}%` },
      { label: "Random trials", value: state.benchmarkRandomTrials },
      { label: "Random seed", value: state.benchmarkRandomSeed ?? "AUTO" },
    ],
  });

  sections.push({
    title: "Primer Design",
    items: [
      { label: "Succeeded", value: `${successCount}/${totalCount}` },
      { label: "Tm condition met", value: `${tmMet}/${successCount}`, warn: tmMet < successCount },
      ...(failCount > 0 ? [{ label: "Failed", value: failCount, warn: true }] : []),
    ],
  });

  if (rescueTotal > 0) {
    sections.push({
      title: "Position Rescue",
      items: [
        {
          label: "Position coverage",
          value: state.rescueStats.positions_attempted > 0
            ? `${rescueTotal}/${state.rescueStats.positions_attempted} rescued`
            : "0",
        },
        ...(state.rescueStats.pool_cascade > 0
          ? [{ label: "Pool cascade", value: `${state.rescueStats.pool_cascade} (${state.rescueStats.pool_variants_tried} tried)` }]
          : []),
        ...(state.rescueStats.auto_relax > 0
          ? [{ label: "Auto-relax (+/-3->+/-5C)", value: state.rescueStats.auto_relax }]
          : []),
        ...(failCount > 0 ? [{ label: "Still failed", value: failCount, warn: true }] : []),
        ...(rescuePenalties.length > 0
          ? [{
            label: "Rescued avg penalty",
            value: `${avgRescuePenalty.toFixed(1)} vs ${avgNormalPenalty.toFixed(1)} normal`,
            warn: avgRescuePenalty > avgNormalPenalty * 1.5,
          }]
          : []),
      ],
    });
  }

  if (fwdTms.length > 0) {
    sections.push({
      title: "Tm Distribution",
      items: [
        { label: "Forward", value: `${avg(fwdTms).toFixed(1)} ± ${std(fwdTms).toFixed(1)} °C` },
        { label: "Reverse", value: `${avg(revTms).toFixed(1)} ± ${std(revTms).toFixed(1)} °C` },
        { label: "Overlap", value: `${avg(ovTms).toFixed(1)} ± ${std(ovTms).toFixed(1)} °C` },
      ],
    });
  }

  if (Object.keys(state.domainStats).length > 0) {
    sections.push({
      title: "Domain Allocation",
      items: Object.entries(state.domainStats).map(([name, stat]) => ({
        label: name,
        value: `${stat.selected}/${stat.quota}`,
        warn: stat.selected < stat.quota,
      })),
    });
  }

  if (failCount > 0) {
    sections.push({
      title: "Failed Mutations",
      items: state.failedMutations.map((failed) => ({
        label: failed.mutation,
        value: failed.reason,
        warn: true,
      })),
    });
  }

  return {
    exported_at: new Date().toISOString(),
    summary: {
      success_count: successCount,
      total_count: totalCount,
      success_rate: totalCount > 0 ? Math.round(successCount / totalCount * 100) : 0,
    },
    sections,
  };
}

function buildBenchmarkRawData(state: AppState, results: Record<string, BenchmarkResult> | null) {
  if (!results || Object.keys(state.yPredMap).length === 0) {
    return null;
  }
  const activeDomains = state.domains.filter(
    (domain) => !state.disabledDomains.includes(`${domain.name}-${domain.start}`),
  );
  const excludedDomains = state.domains.filter(
    (domain) => state.disabledDomains.includes(`${domain.name}-${domain.start}`),
  );
  const landscape = Object.entries(state.yPredMap)
    .map(([variant, fitness]) => ({ variant, fitness }))
    .sort((a, b) => b.fitness - a.fitness);

  return {
    exported_at: new Date().toISOString(),
    settings: {
      n_select: Math.max(1, state.maxPrimers),
      top_percentile: state.benchmarkTopPercentile,
      random_trials: state.benchmarkRandomTrials,
      random_seed: state.benchmarkRandomSeed,
      domain_strategy: state.domainStrategy,
      distance_mode: state.distanceMode,
      pareto_pool_multiplier: state.paretoPoolMultiplier,
      entropy_weight: state.entropyWeightEnabled ? state.entropyWeight : 0,
    },
    domains: {
      active: activeDomains,
      excluded: excludedDomains,
    },
    landscape,
    results,
  };
}

export const createExportSlice: StateCreator<AppState, [], [], ExportSlice> = (set, get) => ({
  plateMappings: [],
  dedupInfo: {},
  progress: 0,
  statusMessage: "Ready",
  tableSorting: [],
  isExporting: false,

  getPlateMap: async () => {
    try {
      const result = await sendRequest("get_plate_map", {});
      set({
        plateMappings: result.mappings,
        dedupInfo: result.dedup_info,
      });
    } catch (err) {
      set({ statusMessage: `Plate map failed: ${formatError(err)}` });
    }
  },

  exportExcel: async (filepath: string, projectId?: string) => {
    const _exportStartedAt = Date.now();
    set({ isExporting: true });
    try {
      const state = get();
      const { designResults, plateMappings, dedupInfo, tableSorting } = state;
      const sortedMuts = getSortedMutations(designResults, tableSorting, {
        yPredMap: state.yPredMap,
        customCandidates: state.customCandidates,
      });
      const ordered = reorderMappings(plateMappings, dedupInfo, sortedMuts);
      const reportData = buildReportData(state);
      const benchmarkRaw = buildBenchmarkRawData(state, state.benchmarkResults);

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

      const rescuedInfo = state.rescuedMutationDetails.length > 0
        ? state.rescuedMutationDetails
        : undefined;

      await sendRequest("export_excel", {
        filepath,
        mappings: enriched,
        dedup_info: dedupInfo,
        report_data: reportData,
        ...(benchmarkRaw ? { benchmark_raw: benchmarkRaw } : {}),
        ...(projectId ? { project_id: projectId, kuma_version: "0.02.02" } : {}),
        ...(rescuedInfo ? { rescued_info: rescuedInfo } : {}),
      });
      set({ statusMessage: `Exported Excel: ${filepath}` });
      notifyJobDone({ title: "Excel export complete", description: filepath, durationMs: Date.now() - _exportStartedAt });
    } catch (err) {
      set({ statusMessage: `Excel export failed: ${formatError(err)}` });
      notifyJobError("Excel export failed", err);
    } finally {
      set({ isExporting: false });
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
    const roundState = useRoundStore.getState();
    const snapshot: WorkspaceV3 = {
      schema_version: "0.3",
      rounds: roundState.rounds,
      active_round_id: roundState.active_round_id,
      inputs: {
        fastaPath: s.fastaPath,
        mutationInputMode: s.mutationInputMode,
        mutationText: s.mutationText,
        evolveproCsvPath: s.evolveproCsvPath,
        selectedGene: s.selectedGene,
      },
      settings: {
        selectedPolymerase: s.selectedPolymerase,
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
        tmTolerance: s.tmTolerance,
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
        overlapMode: s.overlapMode,
        randomSeed: s.randomSeed ?? null,
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
        rescuedMutationDetails: s.rescuedMutationDetails,
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
    return snapshot;
  },

  restoreWorkspace: async (ws: WorkspaceData) => {
    // schema_version "0.3" 이전 워크스페이스는 지원하지 않음
    const wsWithSchema = ws as WorkspaceData & { schema_version?: string };
    if (!wsWithSchema.schema_version || wsWithSchema.schema_version < "0.3") {
      throw new Error(
        i18next.t("exportSlice.legacyWorkspaceUnsupported")
      );
    }
    // schema_version >= "0.3" 이면 WorkspaceV3이므로 legacy normalize는 불필요.
    // 하지만 기존 KURO 상태 복원에 normalizeWorkspace 로직을 재활용한다.
    // WorkspaceV3의 inputs/settings/results/ui 구조는 WorkspaceV2와 동일하므로 안전.
    const normalized = normalizeWorkspace(ws as WorkspaceV1 | WorkspaceV2);
    const { inputs, settings, results, ui, cache } = normalized;
    let loadedSeqInfo: SequenceInfo | null = null;
    let restoredGene = "";

    if (inputs.fastaPath) {
      const info = await sendRequest("load_fasta", {
        filepath: inputs.fastaPath,
      });
      loadedSeqInfo = info;
      if (inputs.selectedGene) {
        const geneExists = info.genes.some(
          (g) => String(g.cds_start) === String(inputs.selectedGene),
        );
        if (geneExists) {
          restoredGene = inputs.selectedGene;
        }
      }
    }

    let preloadedYPred: Record<string, number> | null = null;
    let preloadedPoolVariants: string[] | null = null;
    let evolveproReloadError: string | null = null;
    if (inputs.evolveproCsvPath) {
      try {
        const sendCount = settings.maxPrimers ?? 95;
        const result = await sendRequest("load_evolvepro_csv", {
          filepath: inputs.evolveproCsvPath,
          top_n: (settings.fillOnFailure ?? true) ? sendCount * 2 : sendCount,
        });
        const yPredMap: Record<string, number> = {};
        if (Array.isArray(result.variants) && Array.isArray(result.y_preds)) {
          (result.variants as string[]).forEach((v: string, i: number) => {
            yPredMap[v] = (result.y_preds as number[])[i] ?? 0;
          });
        }
        preloadedYPred = yPredMap;
        preloadedPoolVariants = (result.pool_variants as string[]) ?? [];
      } catch (err) {
        evolveproReloadError = formatError(err);
      }
    }

    const store = get();
    store.resetAll();
    set({
      mutationInputMode: inputs.mutationInputMode ?? "text",
      mutationText: inputs.mutationText ?? "",
      evolveproCsvPath: inputs.evolveproCsvPath ?? "",
      fastaPath: inputs.fastaPath ?? "",
      seqInfo: loadedSeqInfo,
      selectedGene: restoredGene,
      backendDesignStateSynced: false,
      codonStrategy: settings.codonStrategy ?? "closest",
      maxPrimers: settings.maxPrimers ?? 95,
      designResults: results.designResults ?? [],
      successCount: results.successCount ?? 0,
      totalCount: results.totalCount ?? 0,
      failedMutations: results.failedMutations ?? [],
      plateMappings: results.plateMappings ?? [],
      dedupInfo: results.dedupInfo ?? {},
      tableSorting: ui.tableSorting ?? [],
      manuallySwapped: (() => {
        const rawSwapped = results.manuallySwapped ?? {};
        const safe: Record<string, "fwd" | "rev" | "both"> = {};
        for (const [k, v] of Object.entries(rawSwapped)) {
          if (v === "fwd" || v === "rev" || v === "both") safe[k] = v;
        }
        return safe;
      })(),
      customCandidates: results.customCandidates ?? {},
      rescuedMutationDetails: results.rescuedMutationDetails ?? [],
      selectedPolymerase: settings.selectedPolymerase ?? "Benchling",
      tmFwdTarget: settings.tmFwdTarget ?? 62,
      tmRevTarget: settings.tmRevTarget ?? 58,
      tmOverlapTarget: settings.tmOverlapTarget ?? 42,
      gcMin: settings.gcMin ?? 40,
      gcMax: settings.gcMax ?? 60,
      primerLenEnabled: settings.primerLenEnabled ?? true,
      fwdLenMin: settings.fwdLenMin ?? 17,
      fwdLenMax: settings.fwdLenMax ?? 39,
      revLenMin: settings.revLenMin ?? 19,
      revLenMax: settings.revLenMax ?? 27,
      fillOnFailure: settings.fillOnFailure ?? true,
      tmTolerance: settings.tmTolerance ?? 4.0,
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
      overlapMode: settings.overlapMode ?? "partial",
      randomSeed: settings.randomSeed ?? null,
      evolveproTotalCount: cache?.evolveproTotalCount ?? 0,
      evolveproFilteredCount: cache?.evolveproFilteredCount ?? null,
      evolveproParetoExchanges: cache?.evolveproParetoExchanges ?? null,
      evolveproStepStats: cache?.evolveproStepStats ?? null,
      benchmarkResults: cache?.benchmarkResults ?? null,
      domainDiversityEnabled: settings.domainDiversityEnabled ?? true,
      domainStrategy: settings.domainStrategy ?? "proportional",
      paretoDiversityEnabled: settings.paretoDiversityEnabled ?? true,
      yPredMap: preloadedYPred ?? {},
      poolVariants: preloadedPoolVariants ?? [],
      statusMessage: evolveproReloadError
        ? `Workspace loaded. EVOLVEpro CSV reload failed: ${evolveproReloadError}`
        : (settings.autoRedesignOnLoad ?? true)
          ? "Workspace loaded. Re-designing to sync backend..."
          : ((results.designResults?.length ?? 0) > 0
              ? "Workspace loaded. Re-design to enable alternatives and primer swapping."
              : "Workspace loaded."),
    });
    if ((settings.autoRedesignOnLoad ?? true) && inputs.mutationText && inputs.fastaPath && !evolveproReloadError) {
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
      randomSeed: null,
      benchmarkRunning: false,
      showBenchmark: false,
      benchmarkResults: null,
      autoRedesignOnLoad: true,
      saveCache: true,
      poolVariants: [],
      parsedMutations: [],
      parseErrors: [],
      selectedGene: "",
      uniprotCandidates: [],
      uniprotSearching: false,
      isDesigning: false,
      backendDesignStateSynced: false,
      designResults: [],
      successCount: 0,
      totalCount: 0,
      failedMutations: [],
      selectedPolymerase: "Benchling",
      codonStrategy: "closest",
      maxPrimers: 95,
      tmFwdTarget: 62,
      tmRevTarget: 58,
      tmOverlapTarget: 42,
      gcMin: 40,
      gcMax: 60,
      primerLenEnabled: true,
      fwdLenMin: 17,
      fwdLenMax: 39,
      revLenMin: 19,
      revLenMax: 27,
      fillOnFailure: true,
      tmTolerance: 4.0,
      overlapMode: "partial",
      manuallySwapped: {},
      customCandidates: {},
      alternativesCache: {},
      rescuedMutations: [],
      structureAccession: "",
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
      isExporting: false,
    });
  },
});
