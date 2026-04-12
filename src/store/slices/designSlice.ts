import type { StateCreator } from "zustand";
import { sendRequest, cancelAndRespawn } from "../../lib/ipc";
import { wellName } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  SdmPrimerResult,
  DesignResult,
  FailedMutation,
  PlateMapping,
  PlateMapResult,
  PolymeraseInfo,
  PolymeraseProfile,
  RescueStats,
  RescuedMutation,
} from "../../types/models";

const EMPTY_RESCUE_STATS: RescueStats = { pool_cascade: 0, auto_relax: 0, positions_attempted: 0, pool_variants_tried: 0 };

export interface DesignSlice {
  // State
  isDesigning: boolean;
  designResults: SdmPrimerResult[];
  successCount: number;
  totalCount: number;
  failedMutations: FailedMutation[];
  polymerases: PolymeraseInfo[];
  selectedPolymerase: string;
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
  fillOnFailure: boolean;
  manuallySwapped: Record<string, "fwd" | "rev" | "both">;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutations: string[];
  rescueStats: RescueStats;
  rescuedMutationDetails: RescuedMutation[];
  showReport: boolean;

  // Actions
  designPrimers: () => Promise<void>;
  setShowReport: (show: boolean) => void;
  cancelDesign: () => Promise<void>;
  getAlternatives: (mutation: string) => Promise<SdmPrimerResult[]>;
  swapPrimer: (mutation: string, candidateIdx: number, swapType?: "both" | "fwd" | "rev") => Promise<void>;
  applyCustomPrimer: (mutation: string, result: SdmPrimerResult) => void;
  addCustomCandidate: (mutation: string, result: SdmPrimerResult) => void;
  removeCustomCandidate: (mutation: string, index: number) => void;
  evaluateCustomPrimer: (mutation: string, fwdSeq: string, revSeq: string, overlapLen?: number) => Promise<SdmPrimerResult | null>;
  retryFailedMutation: (mutation: string, params: Record<string, number | string>) => Promise<SdmPrimerResult[]>;
  addDesignResult: (mutation: string, result: SdmPrimerResult) => void;
  removeDesignResult: (mutation: string, reason: string) => void;
  setCodonStrategy: (strategy: "closest" | "optimal") => void;
  loadPolymerases: () => Promise<void>;
  setSelectedPolymerase: (name: string) => Promise<void>;
  saveCustomPolymerase: (profile: PolymeraseProfile) => Promise<void>;
  setMaxPrimers: (n: number) => void;
  setTmTargets: (fwd: number, rev: number, ov: number) => void;
  setGcRange: (min: number, max: number) => void;
  setPrimerLenEnabled: (enabled: boolean) => void;
  setPrimerLenRange: (fwdMin: number, fwdMax: number, revMin: number, revMax: number) => void;
  setFillOnFailure: (enabled: boolean) => void;
}

export const createDesignSlice: StateCreator<AppState, [], [], DesignSlice> = (set, get) => ({
  isDesigning: false,
  designResults: [],
  successCount: 0,
  totalCount: 0,
  failedMutations: [],
  polymerases: [],
  selectedPolymerase: "Benchling",
  showReport: false,
  setShowReport: (show: boolean) => set({ showReport: show }),
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
  manuallySwapped: {},
  customCandidates: {},
  rescuedMutations: [] as string[],
  rescueStats: EMPTY_RESCUE_STATS,
  rescuedMutationDetails: [] as RescuedMutation[],

  loadPolymerases: async () => {
    try {
      const polymerases = await sendRequest<PolymeraseInfo[]>("list_polymerases");
      const current = get().selectedPolymerase;
      const names = polymerases.map((p) => p.name);
      const next = names.includes(current) ? current : polymerases[0]?.name ?? current;
      set({ polymerases, selectedPolymerase: next });
      if (next) {
        await get().setSelectedPolymerase(next);
      }
    } catch (err) {
      set({ statusMessage: `Polymerase list load failed: ${formatError(err)}` });
    }
  },

  setSelectedPolymerase: async (name: string) => {
    try {
      const profile = await sendRequest<PolymeraseProfile>("get_polymerase_details", { name });
      set({
        selectedPolymerase: name,
        tmFwdTarget: profile.opt_tm_fwd ?? profile.opt_tm,
        tmRevTarget: profile.opt_tm_rev ?? profile.opt_tm,
        tmOverlapTarget: profile.opt_tm_overlap ?? profile.opt_tm,
        gcMin: profile.min_gc,
        gcMax: profile.max_gc,
      });
    } catch (err) {
      set({ statusMessage: `Polymerase load failed: ${formatError(err)}` });
    }
  },

  saveCustomPolymerase: async (profile: PolymeraseProfile) => {
    try {
      await sendRequest("save_custom_polymerase", { ...profile });
      await get().loadPolymerases();
      await get().setSelectedPolymerase(profile.name);
      set({ statusMessage: `Saved custom polymerase: ${profile.name}` });
    } catch (err) {
      set({ statusMessage: `Custom polymerase save failed: ${formatError(err)}` });
      throw err;
    }
  },

  designPrimers: async () => {
    const state = get();
    const {
      fastaPath,
      selectedGene,
      codonStrategy,
      organism,
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
      fillOnFailure,
      mutationInputMode,
      selectedPolymerase,
    } = state;

    if (!fastaPath) {
      set({ statusMessage: "Sequence file not loaded" });
      return;
    }
    if (!state.mutationText.trim()) {
      set({ statusMessage: "No mutations entered" });
      return;
    }

    // Compute sendCount before CSV reload so EVOLVEpro can fetch buffer candidates
    const sendCount = fillOnFailure
      ? Math.max(Math.ceil(maxPrimers * 1.5), maxPrimers + 20)
      : maxPrimers;
    const isEvolveMode = mutationInputMode === "evolvepro" || mutationInputMode === "multi-evolve";

    if (isEvolveMode && state.evolveproCsvPath) {
      state.cancelDiversityReload();
      // When fill-on-failure is active, load extra buffer candidates beyond maxPrimers
      await state.loadEvolveproCsv(state.evolveproCsvPath, fillOnFailure ? sendCount : undefined);
    }

    // Re-read mutationText after potential CSV reload
    const refreshedText = get().mutationText;

    const allLines = refreshedText.trim().split("\n").filter((l) => l.trim() && !l.trim().startsWith("#"));
    const intendedMuts = new Set(allLines.slice(0, maxPrimers).map((l) => l.trim()));
    const limitedLines = allLines.slice(0, sendCount);
    const limitedText = limitedLines.join("\n");

    const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;

    // Compute rescue pool: pool variants not in intended mutations
    const { poolVariants } = get();
    const rescuePool = poolVariants.filter((v) => !intendedMuts.has(v));

    set({
      isDesigning: true,
      progress: 0,
      statusMessage: "Designing primers...",
      designResults: [],
      plateMappings: [],
      customCandidates: {},
      manuallySwapped: {},
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });

    try {
      const result = await sendRequest<DesignResult>("design_sdm_primers", {
        fasta_path: fastaPath,
        target_start: targetStart,
        mutations_csv_or_text: limitedText,
        polymerase: selectedPolymerase,
        codon_strategy: codonStrategy,
        organism,
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
        ...(rescuePool.length > 0 && { rescue_pool: rescuePool }),
        auto_relax: true,
      }, 300_000);

      const rStats = result.rescue_stats ?? EMPTY_RESCUE_STATS;
      const rMuts = result.rescued_mutations ?? [];
      const rescueTotal = rStats.pool_cascade + rStats.auto_relax;
      const rescueMsg = rescueTotal > 0 ? ` | ${rescueTotal} rescued` : "";
      const rescuedNames = rMuts.map((r) => r.rescued_by);

      // Ensure rescued mutations survive the maxPrimers cap
      const rescuedSet = new Set(rescuedNames);
      const rescued = result.results.filter((r) => rescuedSet.has(r.mutation));
      const nonRescued = result.results.filter((r) => !rescuedSet.has(r.mutation));
      const capped = [...nonRescued.slice(0, maxPrimers - rescued.length), ...rescued];

      const allFailed = result.failed_mutations ?? [];
      const tmMet = capped.filter((r) => r.tm_condition_met).length;
      const intendedFailed = allFailed.filter((f) => intendedMuts.has(f.mutation));
      const failedMsg = intendedFailed.length > 0 ? ` | ${intendedFailed.length} failed` : "";

      set({
        designResults: capped,
        successCount: capped.length,
        totalCount: maxPrimers,
        failedMutations: intendedFailed,
        rescueStats: rStats,
        rescuedMutationDetails: rMuts,
        rescuedMutations: rescuedNames,
        statusMessage: `${capped.length}/${maxPrimers} designed | Tm: ${tmMet}/${capped.length}${failedMsg}${rescueMsg}`,
      });

      // Restore EVOLVEpro mutation list to original maxPrimers count
      if (fillOnFailure && isEvolveMode && get().evolveproCsvPath) {
        await get().loadEvolveproCsv(get().evolveproCsvPath!);
      }

      try {
        const plateResult = await sendRequest<PlateMapResult>("get_plate_map");
        const cappedMuts = new Set(capped.map((r) => r.mutation));
        const filteredMappings = plateResult.mappings.filter((m) =>
          m.primer_type === "reverse" || cappedMuts.has(m.mutation),
        );
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
      if (formatError(err).includes("Sidecar killed")) return;
      set({ statusMessage: `Design failed: ${formatError(err)}` });
    } finally {
      if (get().isDesigning) {
        const hasResults = get().designResults.length > 0;
        set({
          isDesigning: false,
          progress: 100,
          ...(hasResults && { showReport: true }),
        });
      }
    }
  },

  cancelDesign: async () => {
    try {
      await cancelAndRespawn();
      set({
        isDesigning: false,
        progress: 0,
        statusMessage: "Design cancelled",
      });
    } catch (err) {
      set({
        isDesigning: false,
        progress: 0,
        statusMessage: `Design cancelled (reconnecting: ${formatError(err)})`,
      });
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

  setCodonStrategy: (strategy) => set({ codonStrategy: strategy }),
  setMaxPrimers: (n) => set({ maxPrimers: Math.max(1, n) }),

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

  setFillOnFailure: (enabled: boolean) => set({ fillOnFailure: enabled }),

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
        overlap_len: overlapLen ?? 18,
      });
      return result;
    } catch (err) {
      set({ statusMessage: `Evaluate failed: ${formatError(err)}` });
      return null;
    }
  },

  retryFailedMutation: async (mutation: string, params: Record<string, number | string>) => {
    try {
      const { fastaPath, selectedGene } = get();
      const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;
      const result = await sendRequest<{ candidates: SdmPrimerResult[] }>(
        "retry_failed_mutation",
        { mutation, fasta_path: fastaPath, target_start: targetStart, ...params },
      );
      return result.candidates;
    } catch (err) {
      set({ statusMessage: `Retry failed: ${formatError(err)}` });
      return [];
    }
  },

  addDesignResult: (mutation: string, result: SdmPrimerResult) => {
    const { designResults, failedMutations, successCount, rescuedMutations, plateMappings, dedupInfo } = get();

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
    const newFwd: PlateMapping = {
      well: wellName(nextFwdIdx),
      primer_name: `${mutation}_F`,
      sequence: result.forward_seq,
      primer_type: "forward",
      mutation,
    };
    const revExists = plateMappings.some((m) => m.primer_type === "reverse" && m.sequence === result.reverse_seq);
    const newRevMappings: PlateMapping[] = revExists ? [] : [{
      well: wellName(plateMappings.filter((m) => m.primer_type === "reverse").length),
      primer_name: `${mutation}_R`,
      sequence: result.reverse_seq,
      primer_type: "reverse",
      mutation,
    }];
    const newDedupInfo = { ...dedupInfo };
    const revSeq = result.reverse_seq;
    newDedupInfo[revSeq] = [...(newDedupInfo[revSeq] ?? []), mutation];

    const newRescued = rescuedMutations.includes(mutation)
      ? rescuedMutations
      : [...rescuedMutations, mutation];
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
    const { designResults, failedMutations, successCount, rescuedMutations, plateMappings, dedupInfo } = get();
    const removed = designResults.find((r) => r.mutation === mutation);
    if (!removed) return;
    const newDesignResults = designResults.filter((r) => r.mutation !== mutation);
    const newPlateMappings = plateMappings.filter((m) => m.mutation !== mutation);
    const newDedupInfo: Record<string, string[]> = {};
    for (const [seq, muts] of Object.entries(dedupInfo)) {
      const filtered = muts.filter((m) => m !== mutation);
      if (filtered.length > 0) newDedupInfo[seq] = filtered;
    }
    const restoredRank = failedMutations.length > 0
      ? Math.max(...failedMutations.map((f) => f.rank)) + 1
      : newDesignResults.length + 1;
    const newFailed: FailedMutation[] = [
      ...failedMutations,
      { mutation, rank: restoredRank, reason },
    ];
    const newRescued = rescuedMutations.filter((m) => m !== mutation);
    set({
      designResults: newDesignResults,
      failedMutations: newFailed,
      successCount: Math.max(0, successCount - 1),
      plateMappings: newPlateMappings,
      dedupInfo: newDedupInfo,
      rescuedMutations: newRescued,
    });
  },
});
