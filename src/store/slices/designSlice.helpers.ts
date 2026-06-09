import type {
  DesignResult,
  FailedMutation,
  OverlapMode,
  PlateMapping,
  RescueStats,
  RescuedMutation,
  SdmPrimerResult,
} from "../../types/models";
import type { RankedCandidateItem } from "../../types/models.generated";

export const EMPTY_RESCUE_STATS: RescueStats = {
  pool_cascade: 0,
  auto_relax: 0,
  positions_attempted: 0,
  pool_variants_tried: 0,
};

interface PreparedDesignInput {
  intendedMuts: Set<string>;
  limitedText: string;
  sendCount: number;
  isEvolveMode: boolean;
  targetStart: number;
  rescuePool: string[];
}

interface DesignRequestPayload extends Record<string, unknown> {
  fasta_path: string;
  target_start: number;
  mutations_csv_or_text: string;
  polymerase: string;
  codon_strategy: "closest" | "optimal";
  organism: string;
  tm_fwd_target: number;
  tm_rev_target: number;
  tm_overlap_target: number;
  gc_min: number;
  gc_max: number;
  fwd_len_min?: number;
  fwd_len_max?: number;
  rev_len_min?: number;
  rev_len_max?: number;
  overlap_mode: OverlapMode;
  rescue_pool?: string[];
  auto_relax: true;
  seed?: number;
}

interface ProcessedDesignResult {
  capped: SdmPrimerResult[];
  intendedFailed: FailedMutation[];
  rescueStats: RescueStats;
  rescuedMutationDetails: RescuedMutation[];
  rescuedMutations: string[];
  tmMet: number;
  statusMessage: string;
}

/** Default number of extra (buffer) candidates exposed in the picker. */
export const DEFAULT_EVOLVEPRO_EXTRA_EXPOSED = 10;

export function prepareDesignInput(params: {
  mutationText: string;
  maxPrimers: number;
  fillOnFailure: boolean;
  mutationInputMode: "text" | "evolvepro";
  selectedGene: string;
  poolVariants: string[];
  /** EVOLVEpro: user-selected variant list (controls design input when in evolvepro mode). */
  evolveproSelectedVariants?: string[];
  /** EVOLVEpro: ranked candidates for ordering the selection set. */
  evolveproRankedCandidates?: RankedCandidateItem[];
}): PreparedDesignInput {
  const {
    mutationText,
    maxPrimers,
    fillOnFailure,
    mutationInputMode,
    selectedGene,
    poolVariants,
    evolveproSelectedVariants,
    evolveproRankedCandidates,
  } = params;

  const sendCount = fillOnFailure
    ? Math.max(Math.ceil(maxPrimers * 1.5), maxPrimers + 20)
    : maxPrimers;
  const isEvolveMode = mutationInputMode === "evolvepro";

  // In evolvepro mode with an explicit selection set, derive allLines from the
  // selection set ordered by y_pred (ranked_candidates order). This preserves
  // the existing limitedText/rescuePool structure while switching the source.
  let allLines: string[];
  if (isEvolveMode && evolveproSelectedVariants && evolveproSelectedVariants.length > 0) {
    const selectedSet = new Set(evolveproSelectedVariants);
    if (evolveproRankedCandidates && evolveproRankedCandidates.length > 0) {
      // Order by ranked_candidates (already y_pred desc from backend).
      const ranked = evolveproRankedCandidates
        .filter((c) => selectedSet.has(c.variant))
        .map((c) => c.variant);
      // Any selected variants not in ranked_candidates come last.
      const rankedSet = new Set(ranked);
      const unranked = evolveproSelectedVariants.filter((v) => !rankedSet.has(v));
      allLines = [...ranked, ...unranked];
    } else {
      allLines = [...evolveproSelectedVariants];
    }
  } else {
    allLines = mutationText
      .trim()
      .split("\n")
      .filter((l) => l.trim() && !l.trim().startsWith("#"));
  }

  const intendedMuts = new Set(allLines.slice(0, maxPrimers).map((l) => l.trim()));
  const limitedText = allLines.slice(0, sendCount).join("\n");
  const targetStart = selectedGene ? parseInt(selectedGene, 10) : 0;
  const rescuePool = isEvolveMode
    ? poolVariants.filter((v) => !intendedMuts.has(v))
    : [];

  return {
    intendedMuts,
    limitedText,
    sendCount,
    isEvolveMode,
    targetStart,
    rescuePool,
  };
}

export function buildDesignRequestPayload(params: {
  fastaPath: string;
  targetStart: number;
  limitedText: string;
  selectedPolymerase: string;
  codonStrategy: "closest" | "optimal";
  organism: string;
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
  overlapMode: OverlapMode;
  rescuePool: string[];
  tolMax: number;
  randomSeed: number | null;
}): DesignRequestPayload {
  const {
    fastaPath,
    targetStart,
    limitedText,
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
    rescuePool,
    tolMax,
    randomSeed,
  } = params;

  return {
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
    overlap_mode: overlapMode,
    ...(rescuePool.length > 0 && { rescue_pool: rescuePool }),
    tol_max: tolMax,
    auto_relax: true,
    ...(randomSeed !== null && { seed: randomSeed }),
  };
}

export function processDesignResult(params: {
  result: DesignResult;
  maxPrimers: number;
  intendedMuts: Set<string>;
}): ProcessedDesignResult {
  const { result, maxPrimers, intendedMuts } = params;
  const intendedCount = intendedMuts.size;
  const rescueStats = result.rescue_stats ?? EMPTY_RESCUE_STATS;
  const rescuedMutationDetails = result.rescued_mutations ?? [];
  const rescuedMutations = rescuedMutationDetails.map((r) => r.rescued_by);
  const rescuedSet = new Set(rescuedMutations);
  const rescued = result.results.filter((r) => rescuedSet.has(r.mutation));
  const nonRescued = result.results.filter((r) => !rescuedSet.has(r.mutation));
  const rescueSlots = Math.min(rescued.length, maxPrimers);
  const capped = [
    ...nonRescued.slice(0, maxPrimers - rescueSlots),
    ...rescued.slice(0, rescueSlots),
  ];
  const intendedFailed = (result.failed_mutations ?? []).filter((f) => intendedMuts.has(f.mutation));
  const tmMet = capped.filter((r) => r.tm_condition_met).length;

  const rescueTotal = rescueStats.pool_cascade + rescueStats.auto_relax;
  const failedMsg = intendedFailed.length > 0 ? ` | ${intendedFailed.length} failed` : "";
  const rescueMsg = rescueTotal > 0 ? ` | ${rescueTotal} rescued` : "";

  return {
    capped,
    intendedFailed,
    rescueStats,
    rescuedMutationDetails,
    rescuedMutations,
    tmMet,
    statusMessage: `${capped.length}/${intendedCount} designed | Tm: ${tmMet}/${capped.length}${failedMsg}${rescueMsg}`,
  };
}

export function applyCustomPrimerToResults(params: {
  mutation: string;
  result: SdmPrimerResult;
  designResults: SdmPrimerResult[];
}) {
  const { mutation, result, designResults } = params;
  const targetPos = result.aa_position;

  return designResults.map((r) => {
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
      return {
        ...r,
        reverse_seq: result.reverse_seq,
        rev_len: result.rev_len,
        tm_no_rev: result.tm_no_rev,
        gc_rev: result.gc_rev,
      };
    }
    return r;
  });
}

export function rebuildPlateStateFromResults(params: {
  designResults: SdmPrimerResult[];
  wellName: (idx: number) => string;
}) {
  const { designResults, wellName } = params;
  const forwardMappings: PlateMapping[] = [];
  const reverseSeqToMuts: Record<string, string[]> = {};
  const reverseSeqOrder: string[] = [];

  for (const result of designResults) {
    forwardMappings.push({
      well: wellName(forwardMappings.length),
      primer_name: `${result.mutation}_F`,
      sequence: result.forward_seq,
      primer_type: "forward",
      mutation: result.mutation,
    });

    if (!reverseSeqToMuts[result.reverse_seq]) {
      reverseSeqToMuts[result.reverse_seq] = [];
      reverseSeqOrder.push(result.reverse_seq);
    }
    reverseSeqToMuts[result.reverse_seq]!.push(result.mutation);
  }

  const reverseMappings: PlateMapping[] = reverseSeqOrder.map((sequence, index) => {
    const representativeMutation = reverseSeqToMuts[sequence]![0]!;
    return {
      well: wellName(index),
      primer_name: `${representativeMutation}_R`,
      sequence,
      primer_type: "reverse",
      mutation: representativeMutation,
    };
  });

  return {
    plateMappings: [...forwardMappings, ...reverseMappings],
    dedupInfo: reverseSeqToMuts,
  };
}

/** Returns all design results (exclusion feature removed; always all-included). */
export function getIncludedDesignResults(
  designResults: SdmPrimerResult[],
): SdmPrimerResult[] {
  return designResults;
}

/** @deprecated Exclusion feature removed. Always returns []. Kept for workspace migration compat. */
export function pruneExcludedDesignMutations(
  _designResults: SdmPrimerResult[],
  _excludedDesignMutations: string[],
): string[] {
  return [];
}

export function buildIncludedPlateState(params: {
  designResults: SdmPrimerResult[];
  wellName: (idx: number) => string;
}) {
  const { designResults, wellName } = params;
  return rebuildPlateStateFromResults({
    designResults,
    wellName,
  });
}

export function addDesignResultState(params: {
  mutation: string;
  result: SdmPrimerResult;
  designResults: SdmPrimerResult[];
  failedMutations: FailedMutation[];
  rescuedMutations: string[];
  wellName: (idx: number) => string;
  maxPrimers?: number;
  preferredMutations?: Set<string>;
}) {
  const {
    mutation,
    result,
    designResults,
    failedMutations,
    rescuedMutations,
    wellName,
    maxPrimers,
    preferredMutations,
  } = params;

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

  const nextDesignResultsUncapped = [
    ...designResults.map((r) => {
      if (r.aa_position !== fixedResult.aa_position) return r;
      return {
        ...r,
        reverse_seq: fixedResult.reverse_seq,
        rev_len: fixedResult.rev_len,
        tm_no_rev: fixedResult.tm_no_rev,
        gc_rev: fixedResult.gc_rev,
      };
    }),
    fixedResult,
  ];
  const nextDesignResults =
    maxPrimers !== undefined && nextDesignResultsUncapped.length > maxPrimers
      ? trimDesignResults({
          results: nextDesignResultsUncapped,
          maxPrimers,
          mustKeep: mutation,
          preferredMutations,
        })
      : nextDesignResultsUncapped;
  const plateState = buildIncludedPlateState({
    designResults: nextDesignResults,
    wellName,
  });

  return {
    backendDesignStateSynced: false,
    designResults: nextDesignResults,
    failedMutations: failedMutations.filter((f) => f.mutation !== mutation),
    successCount: nextDesignResults.length,
    plateMappings: plateState.plateMappings,
    dedupInfo: plateState.dedupInfo,
    rescuedMutations: rescuedMutations.includes(mutation)
      ? rescuedMutations
      : [...rescuedMutations, mutation],
  };
}

function trimDesignResults(params: {
  results: SdmPrimerResult[];
  maxPrimers: number;
  mustKeep: string;
  preferredMutations?: Set<string>;
}): SdmPrimerResult[] {
  const { results, maxPrimers, mustKeep, preferredMutations } = params;
  const trimmed = [...results];

  while (trimmed.length > maxPrimers) {
    const removableIdx = findLastIndex(trimmed, (r) =>
      r.mutation !== mustKeep && !preferredMutations?.has(r.mutation)
    );
    const fallbackIdx = findLastIndex(trimmed, (r) => r.mutation !== mustKeep);
    const removeIdx = removableIdx >= 0 ? removableIdx : fallbackIdx;
    if (removeIdx < 0) break;
    trimmed.splice(removeIdx, 1);
  }

  return trimmed;
}

function findLastIndex<T>(items: T[], predicate: (item: T) => boolean): number {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (predicate(items[i]!)) return i;
  }
  return -1;
}

export function removeDesignResultState(params: {
  mutation: string;
  reason: string;
  designResults: SdmPrimerResult[];
  failedMutations: FailedMutation[];
  successCount: number;
  rescuedMutations: string[];
  wellName: (idx: number) => string;
}) {
  const {
    mutation,
    reason,
    designResults,
    failedMutations,
    successCount,
    rescuedMutations,
    wellName,
  } = params;

  const removed = designResults.find((r) => r.mutation === mutation);
  if (!removed) return null;

  const newDesignResults = designResults.filter((r) => r.mutation !== mutation);

  const restoredRank = failedMutations.length > 0
    ? Math.max(...failedMutations.map((f) => f.rank)) + 1
    : newDesignResults.length + 1;
  const plateState = buildIncludedPlateState({
    designResults: newDesignResults,
    wellName,
  });

  return {
    backendDesignStateSynced: false,
    designResults: newDesignResults,
    failedMutations: [
      ...failedMutations,
      { mutation, rank: restoredRank, reason },
    ],
    successCount: Math.max(0, successCount - 1),
    plateMappings: plateState.plateMappings,
    dedupInfo: plateState.dedupInfo,
    rescuedMutations: rescuedMutations.filter((m) => m !== mutation),
  };
}
