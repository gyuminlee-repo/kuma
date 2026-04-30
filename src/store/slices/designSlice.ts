import type { StateCreator } from "zustand";
import { cancelAndRespawn, sendRequest } from "../../lib/ipc-kuro";
import { wellName } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import { suggestRetryParams } from "../../lib/primerSuggestion";
import type { AppState } from "../types";
import type {
  SdmPrimerResult,
  PolymeraseProfile,
} from "../../types/models";
import {
  addDesignResultState,
  applyCustomPrimerToResults,
  buildDesignRequestPayload,
  EMPTY_RESCUE_STATS,
  prepareDesignInput,
  processDesignResult,
  rebuildPlateStateFromResults,
  removeDesignResultState,
} from "./designSlice.helpers";

import type { DesignSlice } from "../slice-interfaces";
export type { DesignSlice };

export const createDesignSlice: StateCreator<AppState, [], [], DesignSlice> = (set, get) => ({
  isDesigning: false,
  backendDesignStateSynced: false,
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
  overlapMode: "partial",
  manuallySwapped: {},
  customCandidates: {},
  alternativesCache: {},
  rescuedMutations: [],
  rescueStats: EMPTY_RESCUE_STATS,
  rescuedMutationDetails: [],

  loadPolymerases: async () => {
    try {
      const polymerases = await sendRequest("list_polymerases", {});
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
      const profile = await sendRequest("get_polymerase_details", { name });
      set({
        selectedPolymerase: name,
        tmFwdTarget: profile.opt_tm_fwd ?? profile.opt_tm,
        tmRevTarget: profile.opt_tm_rev ?? profile.opt_tm,
        tmOverlapTarget: profile.opt_tm_overlap ?? profile.opt_tm,
        gcMin: profile.min_gc,
        gcMax: profile.max_gc,
        overlapMode: profile.default_overlap_mode ?? "partial",
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
      overlapMode,
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
      try {
        await state.loadEvolveproCsv(
          state.evolveproCsvPath,
          fillOnFailure ? sendCount : undefined,
        );
      } catch {
        return;
      }
    }

    const prepared = prepareDesignInput({
      mutationText: get().mutationText,
      maxPrimers,
      fillOnFailure,
      mutationInputMode,
      selectedGene: selectedGene ?? "",
      poolVariants: get().poolVariants,
    });
    if (!prepared.limitedText.trim()) {
      set({ statusMessage: "No valid EVOLVEpro variants loaded" });
      return;
    }

    set({
      isDesigning: true,
      backendDesignStateSynced: false,
      progress: 0,
      statusMessage: "Designing primers...",
      designResults: [],
      plateMappings: [],
      customCandidates: {},
      alternativesCache: {},
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
        overlapMode,
        rescuePool: prepared.rescuePool,
      });
      const result = await sendRequest("design_sdm_primers", payload, 300_000);
      if (result.cancelled) {
        set({
          backendDesignStateSynced: false,
          statusMessage: "Design cancelled",
        });
        return;
      }
      const processed = processDesignResult({
        result,
        maxPrimers,
        intendedMuts: prepared.intendedMuts,
      });
      const plateState = rebuildPlateStateFromResults({
        designResults: processed.capped,
        wellName,
      });

      set({
        backendDesignStateSynced: true,
        designResults: processed.capped,
        successCount: processed.capped.length,
        totalCount: prepared.intendedMuts.size,
        failedMutations: processed.intendedFailed,
        rescueStats: processed.rescueStats,
        rescuedMutationDetails: processed.rescuedMutationDetails,
        rescuedMutations: processed.rescuedMutations,
        plateMappings: plateState.plateMappings,
        dedupInfo: plateState.dedupInfo,
        statusMessage: processed.statusMessage,
      });

      if (fillOnFailure && isEvolveMode && get().evolveproCsvPath) {
        await get().loadEvolveproCsv(get().evolveproCsvPath!);
      }

      // Auto-retry failed mutations with suggestion derived from successful primers.
      // Skip when fillOnFailure is on (positions already substituted) or there are no
      // successful primers to derive a suggestion from.
      const postFailed = get().failedMutations;
      if (!fillOnFailure && postFailed.length > 0 && get().designResults.length > 0) {
        await get().autoRetryFailedWithSuggestion();
      }
    } catch (err) {
      if (formatError(err).includes("Sidecar killed")) return;
      set({ statusMessage: `Design failed: ${formatError(err)}` });
    } finally {
      if (get().isDesigning) {
        const hasResults = get().designResults.length > 0;
        set({
          isDesigning: false,
          progress: hasResults ? 100 : 0,
          ...(hasResults && { showReport: true }),
        });
      }
    }
  },

  cancelDesign: async () => {
    try {
      await sendRequest("cancel_design", {});
      set({
        statusMessage: "Cancelling design...",
      });
    } catch (err) {
      try {
        await cancelAndRespawn();
        set({
          statusMessage: `Design cancelled (reconnected after: ${formatError(err)})`,
        });
      } catch (reconnectErr) {
        set({
          isDesigning: false,
          progress: 0,
          backendDesignStateSynced: false,
          statusMessage: `Design cancel failed: ${formatError(reconnectErr)}`,
        });
      }
    }
  },

  getAlternatives: async (mutation: string) => {
    if (!get().backendDesignStateSynced) {
      throw new Error("Re-design the current workspace to load backend alternatives.");
    }
    const cached = get().alternativesCache[mutation];
    if (cached) {
      return cached;
    }
    const result = await sendRequest(
      "get_alternatives",
      { mutation },
    );
    set({
      alternativesCache: {
        ...get().alternativesCache,
        [mutation]: result.candidates,
      },
    });
    return result.candidates;
  },

  swapPrimer: async (mutation: string, candidateIdx: number, swapType: "both" | "fwd" | "rev" = "both") => {
    if (!get().backendDesignStateSynced) {
      set({ statusMessage: "Re-design the current workspace before swapping primers." });
      return;
    }
    const updated = await sendRequest(
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
      newSwapped[mutation] = swapType === "both"
        ? "both"
        : (
            manuallySwapped[mutation] === "both"
            ? "both"
            : manuallySwapped[mutation] && manuallySwapped[mutation] !== swapType
              ? "both"
              : swapType
          );
    }

    const nextDesignResults = designResults.map((r) => {
      if (r.mutation === mutation) return updated;
      if (revChanged && r.aa_position === targetPos) {
        return {
          ...r,
          reverse_seq: updated.reverse_seq,
          rev_len: updated.rev_len,
          tm_no_rev: updated.tm_no_rev,
          gc_rev: updated.gc_rev,
        };
      }
      return r;
    });
    const plateState = rebuildPlateStateFromResults({
      designResults: nextDesignResults,
      wellName,
    });

    set({
      backendDesignStateSynced: true,
      designResults: nextDesignResults,
      plateMappings: plateState.plateMappings,
      dedupInfo: plateState.dedupInfo,
      manuallySwapped: newSwapped,
    });
  },

  applyCustomPrimer: (mutation: string, result: SdmPrimerResult) => {
    const { designResults, manuallySwapped } = get();
    const nextDesignResults = applyCustomPrimerToResults({ mutation, result, designResults });
    const plateState = rebuildPlateStateFromResults({
      designResults: nextDesignResults,
      wellName,
    });

    set({
      backendDesignStateSynced: false,
      designResults: nextDesignResults,
      plateMappings: plateState.plateMappings,
      dedupInfo: plateState.dedupInfo,
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
  setMaxPrimers: (n) => {
    const clamped = Math.max(1, n);
    const state = get();
    const prev = state.maxPrimers;
    set({ maxPrimers: clamped });
    // If an EVOLVEpro CSV failed to load (mutationText cleared but path retained),
    // re-trigger load so user can recover by adjusting the mutation count.
    const isEvolvepro =
      state.mutationInputMode === "evolvepro" || state.mutationInputMode === "multi-evolve";
    const loadFailed =
      isEvolvepro && !!state.evolveproCsvPath && state.evolveproTotalCount === 0 &&
      !state.mutationText.trim();
    if (loadFailed && clamped !== prev) {
      void state.loadEvolveproCsv(state.evolveproCsvPath!);
    }
  },

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

  setOverlapMode: (mode) => set({ overlapMode: mode }),

  evaluateCustomPrimer: async (mutation: string, fwdSeq: string, revSeq: string, overlapLen?: number) => {
    try {
      const { fastaPath, selectedGene } = get();
      const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;
      const result = await sendRequest("evaluate_primer", {
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
      throw err;
    }
  },

  autoRetryFailedWithSuggestion: async () => {
    const state = get();
    const { designResults, failedMutations, codonStrategy } = state;
    if (failedMutations.length === 0 || designResults.length === 0) return;

    const suggestion = suggestRetryParams(designResults, {
      tmFwd: state.tmFwdTarget,
      tmRev: state.tmRevTarget,
      tmOverlap: state.tmOverlapTarget,
      gcMin: state.gcMin,
      gcMax: state.gcMax,
      fwdLenMin: state.fwdLenMin,
      fwdLenMax: state.fwdLenMax,
      revLenMin: state.revLenMin,
      revLenMax: state.revLenMax,
    });

    const params = {
      tm_fwd_target: suggestion.tmFwd,
      tm_rev_target: suggestion.tmRev,
      tm_overlap_target: suggestion.tmOverlap,
      gc_min: suggestion.gcMin,
      gc_max: suggestion.gcMax,
      fwd_len_min: suggestion.fwdLenMin,
      fwd_len_max: suggestion.fwdLenMax,
      rev_len_min: suggestion.revLenMin,
      rev_len_max: suggestion.revLenMax,
      tol_max: suggestion.tolMax,
      codon_strategy: codonStrategy,
    };

    const targets = [...failedMutations];
    set({
      statusMessage: `Auto-retry: trying ${targets.length} failed mutation${targets.length > 1 ? "s" : ""} with suggested parameters...`,
    });

    let rescued = 0;
    for (const failed of targets) {
      // Mutation may already be moved out of failedMutations by a concurrent
      // user action; skip if so.
      if (!get().failedMutations.some((f) => f.mutation === failed.mutation)) continue;
      try {
        const candidates = await get().retryFailedMutation(failed.mutation, params);
        if (candidates.length > 0) {
          get().addDesignResult(failed.mutation, candidates[0]);
          rescued += 1;
        }
      } catch {
        // skip — original failed entry stays untouched
      }
    }

    const remaining = get().failedMutations.length;
    set({
      statusMessage:
        rescued > 0
          ? `Auto-retry: rescued ${rescued}/${targets.length} with suggested parameters · ${remaining} still failed`
          : `Auto-retry found no candidates · ${remaining} still failed`,
    });
  },

  retryFailedMutation: async (mutation: string, params: Record<string, number | string>) => {
    try {
      const { fastaPath, selectedGene, selectedPolymerase, organism } = get();
      const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;
      const result = await sendRequest(
        "retry_failed_mutation",
        {
          mutation,
          fasta_path: fastaPath,
          target_start: targetStart,
          polymerase: selectedPolymerase,
          organism,
          ...params,
        },
      );
      set({
        alternativesCache: {
          ...get().alternativesCache,
          [mutation]: result.candidates,
        },
      });
      return result.candidates;
    } catch (err) {
      set({ statusMessage: `Retry failed: ${formatError(err)}` });
      throw err;
    }
  },

  addDesignResult: (mutation: string, result: SdmPrimerResult) => {
    const { designResults, failedMutations, successCount, rescuedMutations } = get();
    set(addDesignResultState({
      mutation,
      result,
      designResults,
      failedMutations,
      successCount,
      rescuedMutations,
      wellName,
    }));
  },

  removeDesignResult: (mutation: string, reason: string) => {
    const { designResults, failedMutations, successCount, rescuedMutations } = get();
    const nextState = removeDesignResultState({
      mutation,
      reason,
      designResults,
      failedMutations,
      successCount,
      rescuedMutations,
      wellName,
    });
    if (!nextState) return;
    set(nextState);
  },
});
