/**
 * kuroSnapshot.ts, Phase 2: Kuro 자동 저장 스냅샷 빌더 (순수 함수)
 *
 * schema 2부터 `results` 블록(designResults/successCount/totalCount/
 * failedMutations/plateMappings/dedupInfo/manuallySwapped/customCandidates/
 * rescuedMutationDetails)을 함께 저장한다. 필드 목록은 exportSlice
 * getWorkspaceSnapshot의 results 블록과 1:1로 맞춘다.
 * schema 1 스냅샷에는 results가 없으며, 복원 측이 결과물만 비운 채 읽는다.
 *
 * schema 3부터 경로 필드(`sequence_path`, `evolvepro_csv_path`)를 프로젝트 폴더
 * 기준 이식 가능 형태로 저장한다(`lib/projectPath.ts`). 폴더 안을 가리키면
 * `project://` 상대 경로, 밖이면 절대 경로 그대로다. 구 스냅샷은 접두사가 없어
 * 절대 경로로 읽히므로 그대로 호환된다.
 */

import type { AutosaveSnapshot } from "./autosave";
import type { AppState } from "@/store/types";
import { toPortablePath } from "./projectPath";

export const KURO_SCHEMA = 3;

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

/**
 * store 상태에서 직렬화 가능한 kuro 자동 저장 스냅샷을 만든다.
 *
 * @param projectPath 경로 필드를 상대화할 기준 폴더. scratch 세션은 null이며
 *   이때 경로는 절대 경로로 남는다(옮길 대상이 애초에 없다).
 */
export function buildKuroSnapshot(
  state: KuroSnapshotState,
  projectPath: string | null = null,
): AutosaveSnapshot {
  const portable = (value: string): string | null =>
    value ? toPortablePath(projectPath, value) : null;
  return {
    schema: KURO_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    input: {
      sequence_path: portable(state.fastaPath),
      selected_cds: state.selectedGene || null,
      mutation_text: state.mutationText,
      mutation_input_mode: state.mutationInputMode,
      evolvepro_mode: state.evolveproMode,
      evolvepro_csv_path: portable(state.evolveproCsvPath),
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
