import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type { SortingState, Updater } from "@tanstack/react-table";
import type {
  PlateMapping,
  PlateMapResult,
  SequenceInfo,
  WorkspaceV1,
} from "../../types/models";

export interface ExportSlice {
  // State
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
  progress: number;
  statusMessage: string;
  tableSorting: SortingState;

  // Actions
  getPlateMap: () => Promise<void>;
  exportExcel: (filepath: string) => Promise<void>;
  setTableSorting: (updater: Updater<SortingState>) => void;
  setStatus: (msg: string) => void;
  getWorkspaceSnapshot: () => WorkspaceV1;
  restoreWorkspace: (ws: WorkspaceV1) => Promise<void>;
  resetAll: () => void;
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
      version: 1 as const,
      fastaPath: s.fastaPath,
      mutationInputMode: s.mutationInputMode,
      mutationText: s.mutationText,
      evolveproCsvPath: s.evolveproCsvPath,
      selectedGene: s.selectedGene,
      codonStrategy: s.codonStrategy,
      maxPrimers: s.maxPrimers,
      designResults: s.designResults,
      successCount: s.successCount,
      totalCount: s.totalCount,
      failedMutations: s.failedMutations,
      plateMappings: s.plateMappings,
      dedupInfo: s.dedupInfo,
      tableSorting: s.tableSorting,
      manuallySwapped: s.manuallySwapped,
      customCandidates: s.customCandidates,
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
      paretoDiversityEnabled: s.paretoDiversityEnabled || undefined,
      disabledDomains: s.disabledDomains,
      rescuedMutations: s.rescuedMutations,
      entropyWeightEnabled: s.entropyWeightEnabled,
      organism: s.organism,
      pipelineMode: s.pipelineMode,
      positionDiversityEnabled: s.positionDiversityEnabled,
      maxPerPosition: s.maxPerPosition,
    };
  },

  restoreWorkspace: async (ws: WorkspaceV1) => {
    const store = get();
    store.resetAll();
    set({
      mutationInputMode: ws.mutationInputMode ?? "text",
      mutationText: ws.mutationText ?? "",
      evolveproCsvPath: ws.evolveproCsvPath ?? "",
      codonStrategy: ws.codonStrategy ?? "closest",
      maxPrimers: ws.maxPrimers ?? 95,
    });
    if (ws.fastaPath) {
      const info = await sendRequest<SequenceInfo>("load_fasta", { filepath: ws.fastaPath });
      set({ fastaPath: ws.fastaPath, seqInfo: info });
      if (ws.selectedGene) {
        const geneExists = info?.genes.some((g) => String(g.cds_start) === String(ws.selectedGene));
        if (geneExists) set({ selectedGene: ws.selectedGene });
      }
    }
    set({
      designResults: ws.designResults ?? [],
      successCount: ws.successCount ?? 0,
      totalCount: ws.totalCount ?? 0,
      failedMutations: ws.failedMutations ?? [],
      plateMappings: ws.plateMappings ?? [],
      dedupInfo: ws.dedupInfo ?? {},
      tableSorting: (ws.tableSorting ?? []) as SortingState,
      manuallySwapped: (() => {
        const rawSwapped = ws.manuallySwapped ?? {};
        const safe: Record<string, "fwd" | "rev" | "both"> = {};
        for (const [k, v] of Object.entries(rawSwapped)) {
          if (v === "fwd" || v === "rev" || v === "both") safe[k] = v;
        }
        return safe;
      })(),
      customCandidates: ws.customCandidates ?? {},
      tmFwdTarget: ws.tmFwdTarget ?? 62,
      tmRevTarget: ws.tmRevTarget ?? 58,
      tmOverlapTarget: ws.tmOverlapTarget ?? 42,
      gcMin: ws.gcMin ?? 40,
      gcMax: ws.gcMax ?? 60,
      primerLenEnabled: ws.primerLenEnabled ?? false,
      fwdLenMin: ws.fwdLenMin ?? 18,
      fwdLenMax: ws.fwdLenMax ?? 45,
      revLenMin: ws.revLenMin ?? 18,
      revLenMax: ws.revLenMax ?? 30,
      fillOnFailure: ws.fillOnFailure ?? false,
      uniprotAccession: ws.uniprotAccession ?? "",
      domains: ws.domains ?? [],
      ...(ws.disabledDomains && { disabledDomains: ws.disabledDomains }),
      rescuedMutations: ws.rescuedMutations ?? [],
      entropyWeightEnabled: ws.entropyWeightEnabled ?? true,
      ...(ws.organism && { organism: ws.organism }),
      pipelineMode: ws.pipelineMode ?? true,
      positionDiversityEnabled: ws.positionDiversityEnabled ?? true,
      maxPerPosition: ws.maxPerPosition ?? 1,
      domainDiversityEnabled: ws.domainDiversityEnabled ?? true,
      domainStrategy: ws.domainStrategy ?? "proportional",
      paretoDiversityEnabled: ws.paretoDiversityEnabled ?? true,
      statusMessage: "Workspace loaded. Re-designing to sync backend...",
    });
    if (ws.mutationText && ws.fastaPath) {
      await get().designPrimers();
    }
  },

  resetAll: () => {
    // NOTE: Each field below must match its respective slice's initial value.
    // P2: Refactor to per-slice getInitialState() to keep this in sync automatically.
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
      uniprotAccession: "",
      domains: [],
      domainLoading: false,
      disabledDomains: [],
      domainStats: {},
      paretoDiversityEnabled: true,
      entropyWeightEnabled: true,
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
