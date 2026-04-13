import type { StateCreator } from "zustand";
import { sendRequest, cancelAndRespawn } from "../../lib/ipc";
import { wellName } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import type { AppState } from "../types";
import type {
  SdmPrimerResult,
  DesignResult,
  FailedMutation,
  PlateMapResult,
  PolymeraseInfo,
  PolymeraseProfile,
  RescueStats,
  RescuedMutation,
} from "../../types/models";
import {
  addDesignResultState,
  applyCustomPrimerToResults,
  buildDesignRequestPayload,
  EMPTY_RESCUE_STATS,
  filterPlateMappingsForResults,
  prepareDesignInput,
  processDesignResult,
  removeDesignResultState,
} from "./designSlice.helpers";

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

    const initialPrep = prepareDesignInput({
      mutationText: state.mutationText,
      maxPrimers,
      fillOnFailure,
      mutationInputMode,
      selectedGene: selectedGene ?? "",
      poolVariants: state.poolVariants,
    });
    const { sendCount, isEvolveMode } = initialPrep;

    if (isEvolveMode && state.evolveproCsvPath) {
      state.cancelDiversityReload();
      await state.loadEvolveproCsv(state.evolveproCsvPath, fillOnFailure ? sendCount : undefined);
    }

    const prepared = prepareDesignInput({
      mutationText: get().mutationText,
      maxPrimers,
      fillOnFailure,
      mutationInputMode,
      selectedGene: selectedGene ?? "",
      poolVariants: get().poolVariants,
    });

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
      const payload = buildDesignRequestPayload({
        fastaPath,
        targetStart: prepared.targetStart,
        limitedText: prepared.limitedText,
        selectedPolymerase,
        codonStrategy,
        organism,
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
        rescuePool: prepared.rescuePool,
      });
      const result = await sendRequest<DesignResult>("design_sdm_primers", payload, 300_000);
      const processed = processDesignResult({
        result,
        maxPrimers,
        intendedMuts: prepared.intendedMuts,
      });

      set({
        designResults: processed.capped,
        successCount: processed.capped.length,
        totalCount: maxPrimers,
        failedMutations: processed.intendedFailed,
        rescueStats: processed.rescueStats,
        rescuedMutationDetails: processed.rescuedMutationDetails,
        rescuedMutations: processed.rescuedMutations,
        statusMessage: processed.statusMessage,
      });

      if (fillOnFailure && isEvolveMode && get().evolveproCsvPath) {
        await get().loadEvolveproCsv(get().evolveproCsvPath!);
      }

      try {
        const plateResult = await sendRequest<PlateMapResult>("get_plate_map");
        const finalMappings = filterPlateMappingsForResults(plateResult, processed.capped);
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

    set({
      designResults: applyCustomPrimerToResults({ mutation, result, designResults }),
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
    set(addDesignResultState({
      mutation,
      result,
      designResults,
      failedMutations,
      successCount,
      rescuedMutations,
      plateMappings,
      dedupInfo,
      wellName,
    }));
  },

  removeDesignResult: (mutation: string, reason: string) => {
    const { designResults, failedMutations, successCount, rescuedMutations, plateMappings, dedupInfo } = get();
    const nextState = removeDesignResultState({
      mutation,
      reason,
      designResults,
      failedMutations,
      successCount,
      rescuedMutations,
      plateMappings,
      dedupInfo,
    });
    if (!nextState) return;
    set(nextState);
  },
});
