import type { StateCreator } from "zustand";
import { notifyJobComplete } from "../../lib/notify";
import { notifyJobDone, notifyJobError } from "../../lib/toast";
import { startKeepAwake, stopKeepAwake } from "../../lib/keepAwake";
import { cancelAndRespawn, sendRequest } from "../../lib/ipc-kuro";
import { wellName } from "../../lib/plate-utils";
import { formatError } from "../../lib/utils";
import { suggestRetryParams, getStageParams } from "../../lib/primerSuggestion";
import type { AppState } from "../types";
import type {
  SdmPrimerResult,
  PolymeraseProfile,
  RescuedMutation,
} from "../../types/models";
import {
  addDesignResultState,
  applyCustomPrimerToResults,
  buildIncludedPlateState,
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
  // @deprecated Phase C (v0.9.2): legacy popup mount removed; slice kept for
  // DesignReport.tsx Dialog wrapper only. Always init false; never persist.
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
  tmTolerance: 4.0,
  overlapMode: "partial",
  randomSeed: null,
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
        // Method-level SDM targets (Landwehr et al. 2025 SI Fig. S4), mirroring
        // the engine fallback in sdm_engine.py. Never derive from opt_tm.
        tmFwdTarget: profile.opt_tm_fwd ?? 62,
        tmRevTarget: profile.opt_tm_rev ?? 58,
        tmOverlapTarget: profile.opt_tm_overlap ?? 42,
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
      randomSeed,
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
      evolveproSelectedVariants: state.evolveproSelectedVariants,
      evolveproRankedCandidates: state.evolveproRankedCandidates,
    });
    const { sendCount, isEvolveMode } = initialPrep;

    const activeEvolveproPath = state.evolveproMode === "others"
      ? state.othersSourcePath
      : state.evolveproCsvPath;
    if (isEvolveMode && activeEvolveproPath) {
      state.cancelDiversityReload();
      try {
        await state.loadEvolveproCsv(
          activeEvolveproPath,
          fillOnFailure ? sendCount * 2 : undefined,
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
      evolveproSelectedVariants: get().evolveproSelectedVariants,
      evolveproRankedCandidates: get().evolveproRankedCandidates,
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

    const _designStartedAt = Date.now();
    void startKeepAwake("KURO design running");
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
        tolMax: state.tmTolerance,
        randomSeed,
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

      const fillSourcePath = get().evolveproMode === "others"
        ? get().othersSourcePath
        : get().evolveproCsvPath;
      if (fillOnFailure && isEvolveMode && fillSourcePath) {
        await get().loadEvolveproCsv(fillSourcePath);
      }

      const postFailed = get().failedMutations;
      if (postFailed.length === 0 || get().designResults.length === 0) {
        // nothing to retry
      } else if (fillOnFailure && get().evolveproMode !== "topN") {
        await get().cascadeFailedRetry("pipeline-fill");
      } else if (fillOnFailure && get().evolveproMode === "topN") {
        await get().cascadeFailedRetry("topn-fill");
      }
      // fillOnFailure=false: no auto-retry; mutations remain as failed
      // §13: Notify if job took long enough.
      void notifyJobComplete({
        title: "Design complete",
        body: `${get().successCount} primer(s) designed`,
        startedAt: _designStartedAt,
      });
      // §8: In-app toast (always fires, regardless of duration).
      notifyJobDone({
        title: "Design complete",
        description: `${get().successCount} primer(s) designed`,
        durationMs: Date.now() - _designStartedAt,
      });
    } catch (err) {
      if (formatError(err).includes("Sidecar killed")) return;
      set({ statusMessage: `Design failed: ${formatError(err)}` });
      notifyJobError("Design failed", err);
    } finally {
      void stopKeepAwake();
      if (get().isDesigning) {
        const hasResults = get().designResults.length > 0;
        set({
          isDesigning: false,
          progress: hasResults ? 100 : 0,
        });
        // Spec #2/#16: auto-advance to output.summary on success.
        // Legacy popup mount (showReport) removed from AppLayout; report now
        // renders in the right inspector via DesignReportInspector (Phase C).
        if (hasResults) {
          get().setSubStep("output.summary");
        }
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
    const plateState = buildIncludedPlateState({
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
    const plateState = buildIncludedPlateState({
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
    const isEvolvepro = state.mutationInputMode === "evolvepro";
    const activeEvolveproPath = state.evolveproMode === "others"
      ? state.othersSourcePath
      : state.evolveproCsvPath;
    const loadFailed =
      isEvolvepro && !!activeEvolveproPath && state.evolveproTotalCount === 0 &&
      !state.mutationText.trim();
    if (loadFailed && clamped !== prev) {
      void state.loadEvolveproCsv(activeEvolveproPath);
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

  setTmTolerance: (value: number) => {
    const clamped = Math.min(10.0, Math.max(0.5, Math.round(value * 2) / 2));
    set({ tmTolerance: clamped });
  },

  setOverlapMode: (mode) => set({ overlapMode: mode }),

  setRandomSeed: (seed: number | null) => set({ randomSeed: seed }),

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

  cascadeFailedRetry: async (mode) => {
    const startState = get();
    if (startState.failedMutations.length === 0 || startState.designResults.length === 0) return;

    const baseTol = startState.tmTolerance ?? 4.0;
    const baseInput = {
      tmFwd: startState.tmFwdTarget,
      tmRev: startState.tmRevTarget,
      tmOverlap: startState.tmOverlapTarget,
      gcMin: startState.gcMin,
      gcMax: startState.gcMax,
      fwdLenMin: startState.fwdLenMin,
      fwdLenMax: startState.fwdLenMax,
      revLenMin: startState.revLenMin,
      revLenMax: startState.revLenMax,
      baseTol,
    };

    const stages: Array<{
      kind: "same_position" | "diff_position" | "relax";
      relaxStage?: 1 | 2 | 3 | 4;
      label: string;
      badgeType: RescuedMutation["type"];
    }> =
      mode === "pipeline-fill"
        ? [
            { kind: "same_position", label: "Stage 1/6 same-position", badgeType: "same_position" },
            { kind: "diff_position", label: "Stage 2/6 diff-position", badgeType: "diff_position" },
            { kind: "relax", relaxStage: 1, label: "Stage 3/6 length", badgeType: "auto_suggestion_l1" },
            { kind: "relax", relaxStage: 2, label: "Stage 4/6 +GC", badgeType: "auto_suggestion_l2" },
            { kind: "relax", relaxStage: 3, label: "Stage 5/6 +mild Tm", badgeType: "auto_suggestion_l3" },
            { kind: "relax", relaxStage: 4, label: "Stage 6/6 strong", badgeType: "auto_suggestion_l4" },
          ]
        : [
            { kind: "relax", relaxStage: 1, label: "Stage 1/4 length", badgeType: "auto_suggestion_l1" },
            { kind: "relax", relaxStage: 2, label: "Stage 2/4 +GC", badgeType: "auto_suggestion_l2" },
            { kind: "relax", relaxStage: 3, label: "Stage 3/4 +mild Tm", badgeType: "auto_suggestion_l3" },
            { kind: "relax", relaxStage: 4, label: "Stage 4/4 strong", badgeType: "auto_suggestion_l4" },
          ];

    const targets = [...startState.failedMutations];
    let totalRescued = 0;

    const poolVariants = get().poolVariants;
    const usedMutations = new Set<string>(get().designResults.map((r) => r.mutation));
    const usedSubstitutes = new Set<string>();

    for (const stageDef of stages) {
      if (!get().isDesigning) break;
      const remaining = get().failedMutations;
      if (remaining.length === 0) break;

      set({ statusMessage: `Auto-retry: ${stageDef.label} (${remaining.length} remaining)` });

      if (stageDef.kind === "relax" && stageDef.relaxStage) {
        const params = getStageParams(baseInput, stageDef.relaxStage);
        const requestParams = {
          tm_fwd_target: params.tmFwd,
          tm_rev_target: params.tmRev,
          tm_overlap_target: params.tmOverlap,
          gc_min: params.gcMin,
          gc_max: params.gcMax,
          fwd_len_min: params.fwdLenMin,
          fwd_len_max: params.fwdLenMax,
          rev_len_min: params.revLenMin,
          rev_len_max: params.revLenMax,
          tol_max: params.tolMax,
          codon_strategy: get().codonStrategy,
        };
        for (const failed of [...remaining]) {
          if (!get().failedMutations.some((f) => f.mutation === failed.mutation)) continue;
          try {
            const candidates = await get().retryFailedMutation(failed.mutation, requestParams);
            if (candidates.length > 0) {
              const best = candidates[0];
              get().addDesignResult(failed.mutation, best);
              await get().commitDesignResult(failed.mutation, 0);
              set((s) => ({
                rescuedMutationDetails: [
                  ...s.rescuedMutationDetails,
                  {
                    original: failed.mutation,
                    rescued_by: failed.mutation,
                    type: stageDef.badgeType,
                    stage: stageDef.relaxStage,
                    penalty: typeof best.penalty === "number" ? best.penalty : undefined,
                    tolerance_used: typeof best.tolerance_used === "number" ? best.tolerance_used : undefined,
                  },
                ],
              }));
              totalRescued += 1;
            }
          } catch (err) {
            // Intentional: individual mutation failure must not abort cascade for remaining mutations
            console.warn(`[cascade] retry failed for ${failed.mutation}:`, err);
          }
        }
      } else {
        // same_position / diff_position substitution (Task 5)
        for (const failed of [...remaining]) {
          if (!get().failedMutations.some((f) => f.mutation === failed.mutation)) continue;
          const m = failed.mutation.match(/^[A-Z](\d+)[A-Z]$/);
          if (!m) continue;
          const targetPos = parseInt(m[1], 10);

          const candidate = poolVariants.find((v) => {
            if (usedMutations.has(v) || usedSubstitutes.has(v)) return false;
            const vm = v.match(/^[A-Z](\d+)[A-Z]$/);
            if (!vm) return false;
            const vpos = parseInt(vm[1], 10);
            if (stageDef.kind === "same_position") return vpos === targetPos;
            if (stageDef.kind === "diff_position") return vpos !== targetPos;
            return false;
          });
          if (!candidate) continue;

          try {
            const candidates = await get().retryFailedMutation(candidate, {
              codon_strategy: get().codonStrategy,
              tol_max: baseTol,
            });
            if (candidates.length > 0) {
              const best = candidates[0];
              get().addDesignResult(candidate, best);
              await get().commitDesignResult(candidate, 0);
              usedSubstitutes.add(candidate);
              usedMutations.add(candidate);
              set((s) => ({
                rescuedMutationDetails: [
                  ...s.rescuedMutationDetails,
                  {
                    original: failed.mutation,
                    rescued_by: candidate,
                    type: stageDef.badgeType,
                    stage: stageDef.kind === "same_position" ? 1 : 2,
                    substitute: candidate,
                    penalty: typeof best.penalty === "number" ? best.penalty : undefined,
                  },
                ],
                failedMutations: s.failedMutations.filter((f) => f.mutation !== failed.mutation),
              }));
              totalRescued += 1;
            }
          } catch (err) {
            // Intentional: individual substitution failure must not abort cascade for remaining mutations
            console.warn(`[cascade] substitution failed for ${candidate}:`, err);
          }
        }
      }
    }

    set({
      statusMessage:
        totalRescued > 0
          ? `Auto-retry cascade rescued ${totalRescued}/${targets.length}`
          : `Auto-retry cascade found no candidates · ${get().failedMutations.length} still failed`,
    });
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
          const best = candidates[0];
          get().addDesignResult(failed.mutation, best);
          await get().commitDesignResult(failed.mutation, 0);
          // Annotate this mutation as auto-suggestion-rescued so the result
          // table renders a distinct badge instead of the generic remove pill.
          set((s) => ({
            rescuedMutationDetails: [
              ...s.rescuedMutationDetails,
              {
                original: failed.mutation,
                rescued_by: failed.mutation,
                type: "auto_suggestion" as const,
                penalty: typeof best.penalty === "number" ? best.penalty : undefined,
                tolerance_used: typeof best.tolerance_used === "number" ? best.tolerance_used : undefined,
              },
            ],
          }));
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
    const {
      designResults,
      failedMutations,
      rescuedMutations,
      mutationText,
      maxPrimers,
    } = get();
    const preferredMutations = new Set(
      mutationText
        .trim()
        .split("\n")
        .filter((line) => line.trim() && !line.trim().startsWith("#"))
        .slice(0, maxPrimers)
        .map((line) => line.trim()),
    );
    set(addDesignResultState({
      mutation,
      result,
      designResults,
      failedMutations,
      rescuedMutations,
      wellName,
      maxPrimers,
      preferredMutations,
    }));
  },

  commitDesignResult: async (mutation: string, candidateIdx = 0) => {
    // Sync the cascade-rescue candidate into backend _state.results so that
    // Excel export (expected_mutations sheet) includes it.
    try {
      await sendRequest("commit_design_result", {
        mutation,
        candidate_idx: candidateIdx,
      });
      set({ backendDesignStateSynced: true });
    } catch (err) {
      // Commit failure must not roll back frontend state — user already sees
      // the result. Keep backendDesignStateSynced: false so subsequent
      // swap/alternatives calls warn the user to re-design.
      set({ backendDesignStateSynced: false });
      console.warn("[commitDesignResult] backend commit failed for", mutation, err);
    }
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
