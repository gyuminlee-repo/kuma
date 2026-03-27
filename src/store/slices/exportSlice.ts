import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import type { SortingState, Updater } from "@tanstack/react-table";
import type {
  SdmPrimerResult,
  FailedMutation,
  PlateMapping,
  PlateMapResult,
  DomainInfo,
  WorkspaceV1,
} from "../../types/models";

function formatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

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

export const createExportSlice: StateCreator<ExportSlice, [], [], ExportSlice> = (set, get) => ({
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
      const state = get() as unknown as ExportSlice & { designResults: SdmPrimerResult[] };
      const { plateMappings, dedupInfo, tableSorting } = get();
      const sortedMuts = getSortedMutations(state.designResults, tableSorting);
      const ordered = reorderMappings(plateMappings, dedupInfo, sortedMuts);

      const resultByMut = new Map(state.designResults.map((r) => [r.mutation, r]));
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
    const s = get() as unknown as ExportSlice & {
      fastaPath: string;
      mutationInputMode: "text" | "evolvepro";
      mutationText: string;
      evolveproCsvPath: string;
      selectedGene: string;
      codonStrategy: "closest" | "optimal";
      maxPrimers: number;
      designResults: SdmPrimerResult[];
      successCount: number;
      totalCount: number;
      failedMutations: FailedMutation[];
      manuallySwapped: Record<string, "fwd" | "rev" | "both">;
      customCandidates: Record<string, SdmPrimerResult[]>;
      tmFwdTarget: number;
      tmRevTarget: number;
      tmOverlapTarget: number;
      gcMin: number;
      gcMax: number;
      primerLenEnabled: boolean;
      fwdLenMin: number;
      fwdLenMax: number;
      revLenMin: number;
      revLenMax: number;
      fillOnFailure: boolean;
      uniprotAccession: string;
      domains: DomainInfo[];
      domainDiversityEnabled: boolean;
      domainStrategy: "proportional" | "equal";
      paretoDiversityEnabled: boolean;
    };
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
    };
  },

  restoreWorkspace: async (ws: WorkspaceV1) => {
    const all = get() as unknown as ExportSlice & {
      resetAll: () => void;
      loadSequence: (fp: string) => Promise<void>;
      seqInfo: { genes: { cds_start: number }[] } | null;
      designPrimers: () => Promise<void>;
    };
    all.resetAll();
    set({
      mutationInputMode: ws.mutationInputMode ?? "text",
      mutationText: ws.mutationText ?? "",
      evolveproCsvPath: ws.evolveproCsvPath ?? "",
      codonStrategy: ws.codonStrategy ?? "closest",
      maxPrimers: ws.maxPrimers ?? 95,
    } as Partial<ExportSlice>);
    if (ws.fastaPath) {
      await all.loadSequence(ws.fastaPath);
      if (ws.selectedGene) {
        const seqInfo = all.seqInfo;
        const geneExists = seqInfo?.genes.some((g) => String(g.cds_start) === String(ws.selectedGene));
        if (geneExists) set({ selectedGene: ws.selectedGene } as Partial<ExportSlice>);
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
      manuallySwapped: (ws.manuallySwapped ?? {}) as Record<string, "fwd" | "rev" | "both">,
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
      domainDiversityEnabled: ws.domainDiversityEnabled ?? false,
      domainStrategy: ws.domainStrategy ?? "proportional",
      paretoDiversityEnabled: ws.paretoDiversityEnabled ?? false,
      statusMessage: "Workspace loaded. Re-designing to sync backend...",
    } as Partial<ExportSlice>);
    if (ws.mutationText && ws.fastaPath) {
      const store = get() as unknown as { designPrimers: () => Promise<void> };
      await store.designPrimers();
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
      pipelineMode: false,
      positionDiversityEnabled: false,
      maxPerPosition: 1,
      domainDiversityEnabled: false,
      domainStrategy: "proportional",
      uniprotAccession: "",
      domains: [],
      domainLoading: false,
      disabledDomains: new Set<string>(),
      domainStats: {},
      paretoDiversityEnabled: false,
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
      rescuedMutations: new Set<string>(),
      plateMappings: [],
      dedupInfo: {},
      progress: 0,
      statusMessage: "Ready",
      tableSorting: [],
    } as Partial<ExportSlice>);
  },
});
