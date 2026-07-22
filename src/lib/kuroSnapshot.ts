/**
 * kuroSnapshot.ts, Phase 2: Kuro 자동 저장 스냅샷 빌더 (순수 함수)
 *
 * schema 2부터 `results` 블록(designResults/successCount/totalCount/
 * failedMutations/plateMappings/dedupInfo/manuallySwapped/customCandidates/
 * rescuedMutationDetails)을 함께 저장한다. 필드 목록은 exportSlice
 * getWorkspaceSnapshot의 results 블록과 1:1로 맞춘다.
 * schema 1 스냅샷에는 results가 없으며, 복원 측이 결과물만 비운 채 읽는다.
 */

import type { AutosaveSnapshot } from "./autosave";
import type { AppState } from "@/store/types";

export const KURO_SCHEMA = 2;

/** buildKuroSnapshot에 전달하는 store 상태 부분집합 */
export interface KuroSnapshotState
  extends Pick<
    AppState,
    | "fastaPath" | "selectedGene" | "organism"
    | "mutationText" | "mutationInputMode" | "evolveproCsvPath"
    | "evolveproMode" | "evolveproVariantColumn" | "evolveproScoreColumn"
    | "evolveproScoreOrder" | "evolveproSheetName"
    | "uniprotAccession" | "domains" | "disabledDomains"
    | "positionDiversityEnabled" | "maxPerPosition"
    | "domainDiversityEnabled" | "domainStrategy" | "domainOverlapPolicy"
    | "linkerHandling" | "domainQuotaMin"
    | "paretoDiversityEnabled" | "entropyWeightEnabled" | "entropyWeight"
    | "paretoPoolMultiplier" | "distanceMode"
    | "structuralDiversityEnabled" | "structuralKappa"
    | "evolveproRound" | "roundSize" | "autoRedesignOnLoad" | "saveCache"
    | "selectedPolymerase" | "codonStrategy" | "maxPrimers"
    | "tmFwdTarget" | "tmRevTarget" | "tmOverlapTarget"
    | "gcMin" | "gcMax" | "primerLenEnabled"
    | "fwdLenMin" | "fwdLenMax" | "revLenMin" | "revLenMax" | "fillOnFailure"
    | "overlapMode"
    | "designResults" | "successCount" | "totalCount" | "failedMutations"
    | "plateMappings" | "dedupInfo" | "manuallySwapped" | "customCandidates"
    | "rescuedMutationDetails"
  > {}

/** store 상태에서 직렬화 가능한 kuro 자동 저장 스냅샷을 만든다. */
export function buildKuroSnapshot(state: KuroSnapshotState): AutosaveSnapshot {
  return {
    schema: KURO_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    input: {
      sequence_path: state.fastaPath || null,
      selected_cds: state.selectedGene || null,
      mutation_text: state.mutationText,
      mutation_input_mode: state.mutationInputMode,
      evolvepro_mode: state.evolveproMode,
      evolvepro_csv_path: state.evolveproCsvPath || null,
      evolvepro_variant_column: state.evolveproVariantColumn,
      evolvepro_score_column: state.evolveproScoreColumn,
      evolvepro_score_order: state.evolveproScoreOrder,
      evolvepro_sheet_name: state.evolveproSheetName,
      uniprot_accession: state.uniprotAccession || null,
      organism: state.organism,
    },
    parameters: {
      polymerase: state.selectedPolymerase,
      codon_strategy: state.codonStrategy,
      max_primers: state.maxPrimers,
      tm_fwd_target: state.tmFwdTarget,
      tm_rev_target: state.tmRevTarget,
      tm_overlap_target: state.tmOverlapTarget,
      gc_min: state.gcMin,
      gc_max: state.gcMax,
      primer_len_enabled: state.primerLenEnabled,
      fwd_len_min: state.fwdLenMin,
      fwd_len_max: state.fwdLenMax,
      rev_len_min: state.revLenMin,
      rev_len_max: state.revLenMax,
      fill_on_failure: state.fillOnFailure,
      overlap_mode: state.overlapMode,
    },
    diversity: {
      pipeline_mode: state.evolveproMode !== "topN",
      domains: state.domains,
      disabled_domains: state.disabledDomains,
      position_diversity_enabled: state.positionDiversityEnabled,
      max_per_position: state.maxPerPosition,
      domain_diversity_enabled: state.domainDiversityEnabled,
      domain_strategy: state.domainStrategy,
      domain_overlap_policy: state.domainOverlapPolicy,
      linker_handling: state.linkerHandling,
      domain_quota_min: state.domainQuotaMin,
      pareto_diversity_enabled: state.paretoDiversityEnabled,
      structural_diversity_enabled: state.structuralDiversityEnabled,
      structural_kappa: state.structuralKappa,
      entropy_weight_enabled: state.entropyWeightEnabled,
      entropy_weight: state.entropyWeight,
      pareto_pool_multiplier: state.paretoPoolMultiplier,
      distance_mode: state.distanceMode,
      evolvepro_round: state.evolveproRound,
      round_size: state.roundSize,
      auto_redesign_on_load: state.autoRedesignOnLoad,
      save_cache: state.saveCache,
    },
    // schema 2+. exportSlice getWorkspaceSnapshot의 results 블록과 동일 필드.
    results: {
      designResults: state.designResults,
      successCount: state.successCount,
      totalCount: state.totalCount,
      failedMutations: state.failedMutations,
      plateMappings: state.plateMappings,
      dedupInfo: state.dedupInfo,
      manuallySwapped: state.manuallySwapped,
      customCandidates: state.customCandidates,
      rescuedMutationDetails: state.rescuedMutationDetails,
    },
  };
}
