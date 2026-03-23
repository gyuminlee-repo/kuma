import { create } from "zustand";
import { sendRequest, setProgressHandler } from "../lib/ipc";
import { getSortedMutations, reorderMappings, wellName } from "../lib/plate-utils";
import type { SortingState, Updater } from "@tanstack/react-table";

function formatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
import type {
  SequenceInfo,
  ParsedMutation,
  ParseError,
  ParseMutationsResult,
  SdmPrimerResult,
  DesignResult,
  FailedMutation,
  PlateMapping,
  PlateMapResult,
  EvolveproLoadResult,
} from "../types/models";

interface AppState {
  // Input
  fastaPath: string;
  seqInfo: SequenceInfo | null;
  mutationInputMode: "text" | "evolvepro";
  mutationText: string;
  evolveproCsvPath: string;
  positionDiversityEnabled: boolean;
  maxPerPosition: number;
  parsedMutations: ParsedMutation[];
  parseErrors: ParseError[];

  // Parameters
  selectedGene: string;
  codonStrategy: "closest" | "optimal";
  maxPrimers: number;
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

  // Design
  isDesigning: boolean;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];

  // Plate Map
  plateMappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;

  // UI
  progress: number;
  statusMessage: string;
  tableSorting: SortingState;
  manuallySwapped: Record<string, "fwd" | "rev" | "both">;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutations: Set<string>;

  // Actions
  loadSequence: (filepath: string) => Promise<void>;
  setSelectedGene: (gene: string) => void;
  setMutationInputMode: (mode: "text" | "evolvepro") => void;
  setMutationText: (text: string) => void;
  setPositionDiversityEnabled: (enabled: boolean) => void;
  setMaxPerPosition: (n: number) => void;
  loadEvolveproCsv: (filepath: string) => Promise<void>;
  setCodonStrategy: (strategy: "closest" | "optimal") => void;
  setMaxPrimers: (n: number) => void;
  parseMutations: () => Promise<void>;
  designPrimers: () => Promise<void>;
  getAlternatives: (mutation: string) => Promise<SdmPrimerResult[]>;
  swapPrimer: (mutation: string, candidateIdx: number, swapType?: "both" | "fwd" | "rev") => Promise<void>;
  applyCustomPrimer: (mutation: string, result: SdmPrimerResult) => void;
  addCustomCandidate: (mutation: string, result: SdmPrimerResult) => void;
  removeCustomCandidate: (mutation: string, index: number) => void;
  getPlateMap: () => Promise<void>;
  exportExcel: (filepath: string) => Promise<void>;
  setTableSorting: (updater: Updater<SortingState>) => void;
  setStatus: (msg: string) => void;
  setTmTargets: (fwd: number, rev: number, ov: number) => void;
  setGcRange: (min: number, max: number) => void;
  setPrimerLenEnabled: (enabled: boolean) => void;
  setPrimerLenRange: (fwdMin: number, fwdMax: number, revMin: number, revMax: number) => void;
  getWorkspaceSnapshot: () => import("../types/models").WorkspaceV1;
  restoreWorkspace: (ws: import("../types/models").WorkspaceV1) => Promise<void>;
  resetAll: () => void;
  evaluateCustomPrimer: (mutation: string, fwdSeq: string, revSeq: string, overlapLen?: number) => Promise<SdmPrimerResult | null>;
  addDesignResult: (mutation: string, result: SdmPrimerResult) => void;
  removeDesignResult: (mutation: string, reason: string) => void;
}

const INITIAL_STATE = {
  fastaPath: "",
  seqInfo: null as SequenceInfo | null,
  mutationInputMode: "text" as "text" | "evolvepro",
  mutationText: "",
  evolveproCsvPath: "",
  positionDiversityEnabled: false,
  maxPerPosition: 1,
  parsedMutations: [] as ParsedMutation[],
  parseErrors: [] as ParseError[],
  selectedGene: "",
  codonStrategy: "closest" as "closest" | "optimal",
  maxPrimers: 95,
  tmFwdTarget: 62,
  tmRevTarget: 58,
  tmOverlapTarget: 42,
  gcMin: 40,
  gcMax: 60,
  primerLenEnabled: false,
  fwdLenMin: 12,
  fwdLenMax: 45,
  revLenMin: 12,
  revLenMax: 30,
  isDesigning: false,
  designResults: [] as SdmPrimerResult[],
  successCount: 0,
  totalCount: 0,
  failedMutations: [] as FailedMutation[],
  plateMappings: [] as PlateMapping[],
  dedupInfo: {} as Record<string, string[]>,
  progress: 0,
  statusMessage: "Ready",
  tableSorting: [] as import("@tanstack/react-table").SortingState,
  manuallySwapped: {} as Record<string, "fwd" | "rev" | "both">,
  customCandidates: {} as Record<string, SdmPrimerResult[]>,
  rescuedMutations: new Set<string>() as Set<string>,
};

export const useAppStore = create<AppState>((set, get) => {
  setProgressHandler((p) => {
    set({ progress: p.value, statusMessage: p.message });
  });

  return {
    ...INITIAL_STATE,

    loadSequence: async (filepath: string) => {
      try {
        set({ statusMessage: "Loading sequence file..." });
        const info = await sendRequest<SequenceInfo>("load_fasta", { filepath });

        // Auto-select: pick gene with longest aa_length
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
          statusMessage: `Loaded: ${info.header} (${info.seq_length} bp) | ${info.genes.length} gene(s) | Target: ${bestGene?.gene ?? "none"}`,
        });
      } catch (err) {
        set({ statusMessage: `Sequence file load failed: ${formatError(err)}` });
      }
    },

    setSelectedGene: (gene: string) => set({ selectedGene: gene }),
    setMutationInputMode: (mode) => set({ mutationInputMode: mode }),
    setMutationText: (text) => set({ mutationText: text }),

    setPositionDiversityEnabled: (enabled: boolean) => {
      set({ positionDiversityEnabled: enabled });
      // Re-load CSV if available
      const { evolveproCsvPath } = get();
      if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
    },

    setMaxPerPosition: (n: number) => {
      set({ maxPerPosition: Math.max(1, n) });
      // Re-load CSV if available
      const { evolveproCsvPath } = get();
      if (evolveproCsvPath) get().loadEvolveproCsv(evolveproCsvPath);
    },

    loadEvolveproCsv: async (filepath: string) => {
      try {
        const { positionDiversityEnabled, maxPerPosition } = get();
        set({ statusMessage: "Loading EVOLVEpro CSV...", evolveproCsvPath: filepath });
        const result = await sendRequest<EvolveproLoadResult>(
          "load_evolvepro_csv",
          {
            filepath,
            top_n: 9999,
            ...(positionDiversityEnabled && { max_per_position: maxPerPosition }),
          },
        );
        const variantText = result.variants.join("\n");
        const filteredMsg = result.filtered_count
          ? ` (${result.filtered_count} filtered, max ${maxPerPosition}/pos)`
          : "";
        set({
          mutationText: variantText,
          mutationInputMode: "evolvepro",
          statusMessage: `EVOLVEpro: ${result.selected_count}/${result.total_count} variants${filteredMsg}`,
        });
      } catch (err) {
        set({ statusMessage: `EVOLVEpro CSV load failed: ${formatError(err)}` });
      }
    },
    setCodonStrategy: (strategy) => set({ codonStrategy: strategy }),
    setMaxPrimers: (n) => set({ maxPrimers: Math.max(1, n) }),

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

    designPrimers: async () => {
      const {
        fastaPath,
        selectedGene,
        mutationText,
        codonStrategy,
        maxPrimers,
        tmFwdTarget,
        tmRevTarget,
        tmOverlapTarget,
        gcMin,
        gcMax,
        primerLenEnabled,
        fwdLenMin,
        fwdLenMax,
        revLenMin,
        revLenMax,
      } = get();

      if (!fastaPath) {
        set({ statusMessage: "Sequence file not loaded" });
        return;
      }
      if (!mutationText.trim()) {
        set({ statusMessage: "No mutations entered" });
        return;
      }

      // Send all mutations — maxPrimers caps the final success count, not the input
      const allLines = mutationText.trim().split("\n").filter((l) => l.trim() && !l.trim().startsWith("#"));
      const limitedText = allLines.join("\n");

      // Resolve CDS start from selected gene (selectedGene stores cds_start as string)
      const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;

      set({
        isDesigning: true,
        progress: 0,
        statusMessage: "Designing primers...",
        designResults: [],
        plateMappings: [],
        customCandidates: {},
        manuallySwapped: {},
      });

      try {
        const result = await sendRequest<DesignResult>("design_sdm_primers", {
          fasta_path: fastaPath,
          target_start: targetStart,
          mutations_csv_or_text: limitedText,
          polymerase: "Benchling",
          codon_strategy: codonStrategy,
          tm_fwd_target: tmFwdTarget,
          tm_rev_target: tmRevTarget,
          tm_overlap_target: tmOverlapTarget,
          gc_min: gcMin,
          gc_max: gcMax,
          ...(primerLenEnabled && {
            fwd_len_min: fwdLenMin,
            fwd_len_max: fwdLenMax,
            rev_len_min: revLenMin,
            rev_len_max: revLenMax,
          }),
        });

        // Cap successful results to maxPrimers
        const capped = result.results.slice(0, maxPrimers);
        const failed = result.failed_mutations ?? [];
        const tmMet = capped.filter((r) => r.tm_condition_met).length;
        const extraSuccesses = result.results.length - capped.length;
        const failedMsg = failed.length > 0 ? ` | ${failed.length} failed` : "";
        const extraMsg = extraSuccesses > 0 ? ` | ${extraSuccesses} extra` : "";

        set({
          designResults: capped,
          successCount: capped.length,
          totalCount: result.total_count,
          failedMutations: failed,
          statusMessage: `${capped.length}/${result.total_count} designed | Tm: ${tmMet}/${capped.length}${failedMsg}${extraMsg}`,
        });

        // Auto-fetch plate map (non-fatal) — filter to capped mutations only
        try {
          const plateResult =
            await sendRequest<PlateMapResult>("get_plate_map");
          const cappedMuts = new Set(capped.map((r) => r.mutation));
          const filteredMappings = plateResult.mappings.filter((m) =>
            m.primer_type === "reverse" || cappedMuts.has(m.mutation),
          );
          // Also filter reverse mappings: keep only those whose sequence is used by capped mutations
          const cappedRevSeqs = new Set<string>();
          for (const [seq, muts] of Object.entries(plateResult.dedup_info)) {
            if (muts.some((mut) => cappedMuts.has(mut))) cappedRevSeqs.add(seq);
          }
          const finalMappings = filteredMappings.filter((m) =>
            m.primer_type === "forward" || cappedRevSeqs.has(m.sequence),
          );
          set({
            plateMappings: finalMappings,
            dedupInfo: plateResult.dedup_info,
          });
        } catch (plateErr) {
          console.warn("[plate map]", formatError(plateErr));
        }
      } catch (err) {
        set({ statusMessage: `Design failed: ${formatError(err)}` });
      } finally {
        set({ isDesigning: false, progress: 100 });
      }
    },

    getAlternatives: async (mutation: string) => {
      const result = await sendRequest<{ candidates: SdmPrimerResult[] }>(
        "get_alternatives",
        { mutation },
      );
      return result.candidates;
    },

    swapPrimer: async (mutation: string, candidateIdx: number, swapType: "both" | "fwd" | "rev" = "both") => {
      const updated = await sendRequest<SdmPrimerResult>(
        "swap_primer",
        { mutation, candidate_idx: candidateIdx, swap_type: swapType },
      );
      const { designResults, manuallySwapped } = get();
      const targetPos = updated.aa_position;
      const revChanged = swapType === "rev" || swapType === "both";

      // If swapping back to candidate #0 (default best), clear the highlight
      const newSwapped = { ...manuallySwapped };
      if (candidateIdx === 0) {
        delete newSwapped[mutation];
      } else {
        newSwapped[mutation] = swapType === "both" ? "both" : (
          manuallySwapped[mutation] === "both" ? "both" :
          manuallySwapped[mutation] && manuallySwapped[mutation] !== swapType ? "both" : swapType
        );
      }

      set({
        designResults: designResults.map((r) => {
          if (r.mutation === mutation) return updated;
          // Propagate reverse to same-position mutations
          if (revChanged && r.aa_position === targetPos) {
            return { ...r, reverse_seq: updated.reverse_seq, rev_len: updated.rev_len, tm_no_rev: updated.tm_no_rev, gc_rev: updated.gc_rev };
          }
          return r;
        }),
        manuallySwapped: newSwapped,
      });
    },

    applyCustomPrimer: (mutation: string, result: SdmPrimerResult) => {
      const { designResults, manuallySwapped } = get();
      const targetPos = result.aa_position;

      set({
        designResults: designResults.map((r) => {
          if (r.mutation === mutation) {
            // Preserve server-provided candidate counts (displayed count is server count + customCandidates.length)
            // Also preserve identity fields (mutation, aa_position, codon_pos) from the original row
            // so that evaluate_custom_primer's dummy_mut.position=0 cannot corrupt sort order.
            return {
              ...result,
              mutation: r.mutation,
              aa_position: r.aa_position,
              codon_pos: r.codon_pos,
              candidate_count: r.candidate_count,
              candidate_fwd_count: r.candidate_fwd_count,
              candidate_rev_count: r.candidate_rev_count,
            };
          }
          // Propagate reverse to same-position mutations
          if (r.aa_position === targetPos) {
            return { ...r, reverse_seq: result.reverse_seq, rev_len: result.rev_len, tm_no_rev: result.tm_no_rev, gc_rev: result.gc_rev };
          }
          return r;
        }),
        manuallySwapped: { ...manuallySwapped, [mutation]: "both" },
      });
    },

    addCustomCandidate: (mutation: string, result: SdmPrimerResult) => {
      const { customCandidates } = get();
      const existing = customCandidates[mutation] ?? [];
      // Count is computed dynamically in ResultTable from customCandidates length;
      // do NOT mutate designResults here to avoid count drift on remove.
      set({
        customCandidates: { ...customCandidates, [mutation]: [...existing, result] },
      });
    },

    removeCustomCandidate: (mutation: string, index: number) => {
      const { customCandidates } = get();
      const existing = customCandidates[mutation] ?? [];
      set({
        customCandidates: {
          ...customCandidates,
          [mutation]: existing.filter((_, i) => i !== index),
        },
      });
    },

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
        const { plateMappings, dedupInfo, designResults, tableSorting } = get();
        const sortedMuts = getSortedMutations(designResults, tableSorting);
        const ordered = reorderMappings(plateMappings, dedupInfo, sortedMuts);

        // Enrich mappings with Tm/codon data from designResults
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

    setTmTargets: (fwd: number, rev: number, ov: number) => {
      set({ tmFwdTarget: fwd, tmRevTarget: rev, tmOverlapTarget: ov });
    },

    setGcRange: (min: number, max: number) => {
      set({ gcMin: min, gcMax: max });
    },

    setPrimerLenEnabled: (enabled: boolean) => set({ primerLenEnabled: enabled }),

    setPrimerLenRange: (fwdMin: number, fwdMax: number, revMin: number, revMax: number) => {
      set({ fwdLenMin: fwdMin, fwdLenMax: fwdMax, revLenMin: revMin, revLenMax: revMax });
    },

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
      };
    },

    restoreWorkspace: async (ws) => {
      get().resetAll();
      set({
        mutationInputMode: ws.mutationInputMode ?? "text",
        mutationText: ws.mutationText ?? "",
        evolveproCsvPath: ws.evolveproCsvPath ?? "",
        codonStrategy: ws.codonStrategy ?? "closest",
        maxPrimers: ws.maxPrimers ?? 95,
      });
      if (ws.fastaPath) {
        await get().loadSequence(ws.fastaPath);
        if (ws.selectedGene) {
          const seqInfo = get().seqInfo;
          const geneExists = seqInfo?.genes.some((g) => String(g.cds_start) === String(ws.selectedGene));
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
        manuallySwapped: (ws.manuallySwapped ?? {}) as Record<string, "fwd" | "rev" | "both">,
        customCandidates: ws.customCandidates ?? {},
        tmFwdTarget: ws.tmFwdTarget ?? 62,
        tmRevTarget: ws.tmRevTarget ?? 58,
        tmOverlapTarget: ws.tmOverlapTarget ?? 42,
        gcMin: ws.gcMin ?? 40,
        gcMax: ws.gcMax ?? 60,
        primerLenEnabled: ws.primerLenEnabled ?? false,
        fwdLenMin: ws.fwdLenMin ?? 12,
        fwdLenMax: ws.fwdLenMax ?? 45,
        revLenMin: ws.revLenMin ?? 12,
        revLenMax: ws.revLenMax ?? 30,
        statusMessage: "Workspace loaded. Re-designing to sync backend...",
      });
      if (ws.mutationText && ws.fastaPath) {
        await get().designPrimers();
      }
    },

    resetAll: () => {
      set({ ...INITIAL_STATE });
    },

    evaluateCustomPrimer: async (mutation: string, fwdSeq: string, revSeq: string, overlapLen?: number) => {
      try {
        const { fastaPath, selectedGene } = get();
        const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;
        const result = await sendRequest<SdmPrimerResult>("evaluate_primer", {
          mutation,
          fasta_path: fastaPath,
          target_start: targetStart,
          forward_seq: fwdSeq,
          reverse_seq: revSeq,
          overlap_len: overlapLen ?? 20,
        });
        return result;
      } catch (err) {
        set({ statusMessage: `Evaluate failed: ${formatError(err)}` });
        return null;
      }
    },

    addDesignResult: (mutation: string, result: SdmPrimerResult) => {
      const { designResults, failedMutations, successCount, plateMappings, dedupInfo } = get();
      // Parse aa_position from mutation name (e.g. "V100F" → 100) if result has dummy position
      let aaPos = result.aa_position;
      if (!aaPos) {
        const match = mutation.match(/[A-Z](\d+)[A-Z]/);
        if (match) aaPos = parseInt(match[1], 10);
      }
      const fixedResult: SdmPrimerResult = {
        ...result,
        mutation,
        aa_position: aaPos || 0,
        candidate_fwd_count: result.candidate_fwd_count ?? 1,
        candidate_rev_count: result.candidate_rev_count ?? 1,
      };
      const newDesignResults = [...designResults, fixedResult];
      const nextFwdIdx = plateMappings.filter((m) => m.primer_type === "forward").length;
      const newFwd: import("../types/models").PlateMapping = {
        well: wellName(nextFwdIdx),
        primer_name: `${mutation}_F`,
        sequence: result.forward_seq,
        primer_type: "forward",
        mutation,
      };
      // Add rev only if not already present (dedup)
      const revExists = plateMappings.some((m) => m.primer_type === "reverse" && m.sequence === result.reverse_seq);
      const newRevMappings: import("../types/models").PlateMapping[] = revExists ? [] : [{
        well: wellName(plateMappings.filter((m) => m.primer_type === "reverse").length),
        primer_name: `${mutation}_R`,
        sequence: result.reverse_seq,
        primer_type: "reverse",
        mutation,
      }];
      // Update dedup info
      const newDedupInfo = { ...dedupInfo };
      const revSeq = result.reverse_seq;
      newDedupInfo[revSeq] = [...(newDedupInfo[revSeq] ?? []), mutation];

      const newRescued = new Set(get().rescuedMutations);
      newRescued.add(mutation);
      set({
        designResults: newDesignResults,
        failedMutations: failedMutations.filter((f) => f.mutation !== mutation),
        successCount: successCount + 1,
        plateMappings: [...plateMappings, newFwd, ...newRevMappings],
        dedupInfo: newDedupInfo,
        rescuedMutations: newRescued,
      });
    },

    removeDesignResult: (mutation: string, reason: string) => {
      const { designResults, failedMutations, successCount, plateMappings, dedupInfo, rescuedMutations } = get();
      const removed = designResults.find((r) => r.mutation === mutation);
      if (!removed) return;
      const newDesignResults = designResults.filter((r) => r.mutation !== mutation);
      const newPlateMappings = plateMappings.filter((m) => m.mutation !== mutation);
      // Rebuild dedupInfo: remove this mutation from all dedup lists
      const newDedupInfo: Record<string, string[]> = {};
      for (const [seq, muts] of Object.entries(dedupInfo)) {
        const filtered = muts.filter((m) => m !== mutation);
        if (filtered.length > 0) newDedupInfo[seq] = filtered;
      }
      // Restore to failedMutations (preserve original rank or use current rank)
      const restoredRank = failedMutations.length > 0
        ? Math.max(...failedMutations.map((f) => f.rank)) + 1
        : newDesignResults.length + 1;
      const newFailed: import("../types/models").FailedMutation[] = [
        ...failedMutations,
        { mutation, rank: restoredRank, reason },
      ];
      const newRescued = new Set(rescuedMutations);
      newRescued.delete(mutation);
      set({
        designResults: newDesignResults,
        failedMutations: newFailed,
        successCount: Math.max(0, successCount - 1),
        plateMappings: newPlateMappings,
        dedupInfo: newDedupInfo,
        rescuedMutations: newRescued,
      });
    },
  };
});
