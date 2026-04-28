/**
 * kuroSnapshot.ts — Phase 2: Kuro 자동 저장 스냅샷 빌더 (순수 함수)
 * 결과물 필드(designResults/failedMutations/rescueStats/benchmarkResults/rescuedMutations) 제외.
 */

import type { AutosaveSnapshot } from "./autosave";
import type { AppState } from "@/store/types";

export const KURO_SCHEMA = 1;

/** buildKuroSnapshot에 전달하는 store 상태 부분집합 */
export interface KuroSnapshotState
  extends Pick<
    AppState,
    | "fastaPath" | "selectedGene" | "organism"
    | "mutationText" | "mutationInputMode" | "evolveproCsvPath"
    | "uniprotAccession" | "pipelineMode" | "domains" | "disabledDomains"
    | "positionDiversityEnabled" | "maxPerPosition"
    | "domainDiversityEnabled" | "domainStrategy" | "domainOverlapPolicy"
    | "linkerHandling" | "domainQuotaMin"
    | "paretoDiversityEnabled" | "entropyWeightEnabled" | "entropyWeight"
    | "paretoPoolMultiplier" | "distanceMode"
    | "evolveproRound" | "roundSize" | "autoRedesignOnLoad" | "saveCache"
    | "selectedPolymerase" | "codonStrategy" | "maxPrimers"
    | "tmFwdTarget" | "tmRevTarget" | "tmOverlapTarget"
    | "gcMin" | "gcMax" | "primerLenEnabled"
    | "fwdLenMin" | "fwdLenMax" | "revLenMin" | "revLenMax" | "fillOnFailure"
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
      evolvepro_csv_path: state.evolveproCsvPath || null,
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
    },
    diversity: {
      pipeline_mode: state.pipelineMode,
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
      entropy_weight_enabled: state.entropyWeightEnabled,
      entropy_weight: state.entropyWeight,
      pareto_pool_multiplier: state.paretoPoolMultiplier,
      distance_mode: state.distanceMode,
      evolvepro_round: state.evolveproRound,
      round_size: state.roundSize,
      auto_redesign_on_load: state.autoRedesignOnLoad,
      save_cache: state.saveCache,
    },
  };
}
