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
 *
 * schema 4부터 `results` 블록에 `poolVariants`를 추가한다. rescue/fill-on-failure로
 * 채워진 결과의 mutation은 mutationText에 없고 poolVariants에만 있어서, 복원 측
 * divergence 판정이 이 값 없이는 정상 상태를 매번 발산으로 오판했다.
 *
 * schema 5부터 exportSlice.getWorkspaceSnapshot과 비교해 빠져 있던 상태를
 * 마저 채운다. 어디에 무엇을 넣었는지:
 * - `navigation`: currentMajor/currentSubStep/stepStatus. 재시작 후 화면
 *   위치까지 그대로 이어가기 위함(기존에는 결과물 유무로만 휴리스틱 추정했다).
 * - `pipeline`: EVOLVEpro 파생 상태(yPredMap/evolveproSelectedVariants/
 *   evolveproRankedCandidates/evolveproUsedVariantColumn/evolveproUsedScoreColumn/
 *   evolveproTotalCount/evolveproFilteredCount/evolveproParetoExchanges/
 *   evolveproStepStats/domainStats). loadEvolveproCsv 재도출을 건너뛸 때
 *   (아래 `sources` 참조) 이 값들이 재도출 없이 그대로 복원의 정본이 된다.
 *   yPredMap과 evolveproRankedCandidates는 EVOLVEpro pool 크기에 비례해 커질 수
 *   있다(수 MB 사례 존재, AGENTS.md 참조). `saveCache`로 가리지 않는 이유는 아래
 *   pipeline 블록 자체의 주석 참조(재도출을 대체하는 정본이라 "부가 캐시"가
 *   아니다).
 * - `diversity` 확장: refDomains/refDomainHash/structureAccession/
 *   structureLoaded/uniprotCandidates. 도메인 할당·3D 거리 계산의 입력이라
 *   diversity와 같은 성격이다. uniprotCandidates는 지문 일치로 loadSequence를
 *   건너뛸 때(sequenceSlice.loadSequence가 fire-and-forget으로 띄우는
 *   searchUniprot이 통째로 안 돈다) UniProt 패널이 빈 목록을 보게 되는 것을
 *   막는다(2026-08-03 리뷰 지적). `uniprotSearching`은 넣지 않는다, 저장
 *   순간 검색 중이었다면 복원 후 그 값이 그대로 true로 착지해 스피너가 영원히
 *   돌게 된다. 진행 중 플래그는 항상 정지 상태로 재출발해야 안전하다.
 * - `parameters` 확장: tmTolerance/randomSeed.
 * - `benchmark`: benchmarkTopPercentile/benchmarkRandomTrials/
 *   benchmarkRandomSeed. exportSlice에서는 settings에 속하지만 이 파일은
 *   parameters/diversity로 이미 나뉘어 있어 새 블록으로 분리한다.
 * - `results` 확장: rescuedMutations(작음, 항상 저장), alternativesCache와
 *   benchmarkResults(재계산 가능한 큰 캐시, `saveCache`를 따름), showBenchmark.
 * - `ui`: tableSorting.
 * - `sequence_info`: `input.sequence_path`가 가리키는 파일의 load_fasta 응답
 *   원본(JSON)을 그대로 담는다. 복원 시 지문(`sources`)이 일치하면 이 값을
 *   그대로 seqInfo로 써서 loadSequence 재호출(과 그 부수효과인 domains 등
 *   초기화, searchUniprot/annotateReferenceDomains의 지연 착지)을 건너뛴다.
 *   biopython Bio.SeqRecord 파생 유전자 수만큼 커질 수 있으나 서열 1개 기준이라
 *   결과물 배열보다는 작다.
 * - `sources`: 서열 파일과 EVOLVEpro CSV의 `{ size, mtimeMs }` 지문
 *   (`lib/sourceFingerprint.ts`). 복원 측이 현재 파일과 대조해 재도출 필요
 *   여부를 정한다.
 *
 * schema 6부터 liquid-handler controls와 `evolveproExtraExposed`를 저장한다.
 * 전자는 다음 robot mapping의 source-well placement/transfer volume을, 후자는
 * picker의 exposed candidate count를 결정하므로 어느 쪽도 UI-only가 아니다.
 *
 * KURO 스냅샷은 Round 엔티티(`rounds`/`active_round_id`)를 저장하지 않는다.
 * `lib/mame/autosaveSnapshot.ts`의 MAME 스냅샷이 이미 이 상태를 저장·복원하고
 * (`useAutosaveHydration.ts`의 mame 처리 구간) `useMameAutosave.ts`가 round
 * 변경 시 트리거까지 갖추고 있다. 같은 `useRoundStore`에 writer를 두 곳(kuro+
 * mame) 두면 두 스냅샷의 저장 시점이 갈릴 때 나중에 착지한 쪽이 조용히 이기고
 * 어느 쪽이 이겼는지 코드만 보고는 알 수 없다. 한 store는 한 owner(MAME)만
 * 갖는다. Round 저장이 필요해 보이면 MAME 쪽에 이미 있는지 먼저 확인할 것.
 */

import type { AutosaveSnapshot } from "./autosave";
import type { AppState } from "@/store/types";
import type { SourceFingerprint } from "./sourceFingerprint";
import { toPortablePath } from "./projectPath";

export const KURO_SCHEMA = 6;

/** buildKuroSnapshot에 전달하는 store 상태 부분집합 */
export interface KuroSnapshotState
  extends Pick<
    AppState,
    | "fastaPath" | "selectedGene" | "organism" | "seqInfo"
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
    | "refDomains" | "refDomainHash" | "structureAccession" | "structureLoaded"
    | "uniprotCandidates"
    | "evolveproRound" | "roundSize" | "autoRedesignOnLoad" | "saveCache"
    | "selectedPolymerase" | "codonStrategy" | "maxPrimers"
    | "tmFwdTarget" | "tmRevTarget" | "tmOverlapTarget"
    | "gcMin" | "gcMax" | "primerLenEnabled"
    | "fwdLenMin" | "fwdLenMax" | "revLenMin" | "revLenMax" | "fillOnFailure"
    | "overlapMode" | "tmTolerance" | "randomSeed"
    | "echoTransferVol" | "echoQuadrant" | "echoUsedQuadrants" | "janusTransferVol"
    | "benchmarkTopPercentile" | "benchmarkRandomTrials" | "benchmarkRandomSeed"
    | "designResults" | "successCount" | "totalCount" | "failedMutations"
    | "plateMappings" | "dedupInfo" | "manuallySwapped" | "customCandidates"
    | "rescuedMutationDetails" | "poolVariants" | "rescuedMutations"
    | "alternativesCache" | "benchmarkResults" | "showBenchmark"
    | "tableSorting"
    | "currentMajor" | "currentSubStep" | "stepStatus"
    | "yPredMap" | "evolveproSelectedVariants" | "evolveproExtraExposed" | "evolveproRankedCandidates"
    | "evolveproUsedVariantColumn" | "evolveproUsedScoreColumn"
    | "evolveproTotalCount" | "evolveproFilteredCount" | "evolveproParetoExchanges"
    | "evolveproStepStats" | "domainStats"
  > {}

/**
 * buildKuroSnapshot 호출부가 순수 함수 시그니처를 지키며 넘기는 외부 상태.
 *
 * rounds/active_round_id는 여기 없다. 파일 헤더의 "KURO 스냅샷은 Round
 * 엔티티를 저장하지 않는다" 참조(MAME 스냅샷 단독 소유).
 */
export interface KuroSnapshotExtras {
  /** lib/sourceFingerprint.ts. 계산 실패/미계산이면 null. */
  sequenceFingerprint: SourceFingerprint | null;
  evolveproCsvFingerprint: SourceFingerprint | null;
}

const EMPTY_EXTRAS: KuroSnapshotExtras = {
  sequenceFingerprint: null,
  evolveproCsvFingerprint: null,
};

/**
 * store 상태에서 직렬화 가능한 kuro 자동 저장 스냅샷을 만든다.
 *
 * @param projectPath 경로 필드를 상대화할 기준 폴더. scratch 세션은 null이며
 *   이때 경로는 절대 경로로 남는다(옮길 대상이 애초에 없다).
 * @param extras 지문처럼 store를 직접 참조하지 않고는 얻을 수 없는 값.
 *   생략하면 빈 값으로 채운다(단위 테스트 경로).
 */
export function buildKuroSnapshot(
  state: KuroSnapshotState,
  projectPath: string | null = null,
  extras: KuroSnapshotExtras = EMPTY_EXTRAS,
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
      // schema 5+. load_fasta 응답 원본. 지문(sources)이 일치하면 복원 측이
      // loadSequence 재호출 없이 이 값을 그대로 seqInfo로 쓴다(핵심 헤더 참조).
      sequence_info: state.seqInfo,
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
      // schema 5+
      tm_tolerance: state.tmTolerance,
      random_seed: state.randomSeed,
      // schema 6+. These controls determine the source-well placement and
      // transfer volume in exported mappings, so treating them as UI-only
      // would make reopening a project change the next robot sheet.
      echo_transfer_vol: state.echoTransferVol,
      echo_quadrant: state.echoQuadrant,
      echo_used_quadrants: state.echoUsedQuadrants,
      janus_transfer_vol: state.janusTransferVol,
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
      // schema 5+. exportSlice.getWorkspaceSnapshot의 settings 블록과 동일하게
      // saveCache와 무관하게 항상 저장한다(재도출 시 restoreWorkspace가 하는
      // translation-hash 재검증과 같은 이유로 유지값이지 캐시가 아니다).
      ref_domains: state.refDomains,
      ref_domain_hash: state.refDomainHash,
      structure_accession: state.structureAccession,
      structure_loaded: state.structureLoaded,
      // schema 5+. UniProt 검색 결과 후보 목록(2026-08-03 리뷰 지적). 지문
      // 일치로 loadSequence를 건너뛰면 그 fire-and-forget searchUniprot 호출도
      // 안 돌아 이 값을 재생성할 길이 없다, 저장해 두지 않으면 복원 후
      // UniProt 패널이 항상 빈 목록으로 보인다. `uniprotSearching`(진행 중
      // 플래그)은 의도적으로 넣지 않는다: 저장 시점에 검색 중이었다면 그 값이
      // true로 그대로 복원돼 다시 검색이 끝나지 않는 한 스피너가 영원히 돈다.
      uniprot_candidates: state.uniprotCandidates,
    },
    // schema 5+. exportSlice의 settings 블록에서는 별도 필드였으나 이 파일은
    // parameters/diversity로 이미 나뉘어 있어 새 블록으로 분리한다.
    benchmark: {
      benchmark_top_percentile: state.benchmarkTopPercentile,
      benchmark_random_trials: state.benchmarkRandomTrials,
      benchmark_random_seed: state.benchmarkRandomSeed,
    },
    // schema 2+. exportSlice getWorkspaceSnapshot의 results 블록과 동일 필드.
    // schema 4+: poolVariants 추가(divergence 판정에 필요, 위 헤더 주석 참조).
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
      poolVariants: state.poolVariants,
      // schema 5+. rescuedMutations/showBenchmark는 작아서 항상 저장한다.
      // alternativesCache/benchmarkResults는 재설계로 재계산 가능한 큰 캐시라
      // exportSlice.getWorkspaceSnapshot의 cache 블록과 같은 규약으로 saveCache를
      // 따른다(둘 다 designResults 규모까지 커질 수 있다, AGENTS.md 참조).
      rescuedMutations: state.rescuedMutations,
      showBenchmark: state.showBenchmark,
      ...(state.saveCache && {
        alternativesCache: state.alternativesCache,
        benchmarkResults: state.benchmarkResults,
      }),
    },
    // schema 5+. EVOLVEpro 파생 상태. loadEvolveproCsv 재도출을 건너뛸 때(지문
    // 일치) 이 값들이 재도출 없이 그대로 복원의 정본이 된다. yPredMap과
    // evolveproRankedCandidates는 pool 크기에 비례해 커질 수 있으나, 건너뛰기
    // 자체가 이 값 없이는 불가능하므로 saveCache로 가리지 않는다(saveCache는
    // "재도출 가능한 부가 캐시"용 토글이고, 이 블록은 재도출을 대체하는 정본이다).
    pipeline: {
      y_pred_map: state.yPredMap,
      evolvepro_selected_variants: state.evolveproSelectedVariants,
      evolvepro_extra_exposed: state.evolveproExtraExposed,
      evolvepro_ranked_candidates: state.evolveproRankedCandidates,
      evolvepro_used_variant_column: state.evolveproUsedVariantColumn,
      evolvepro_used_score_column: state.evolveproUsedScoreColumn,
      evolvepro_total_count: state.evolveproTotalCount,
      evolvepro_filtered_count: state.evolveproFilteredCount,
      evolvepro_pareto_exchanges: state.evolveproParetoExchanges,
      evolvepro_step_stats: state.evolveproStepStats,
      domain_stats: state.domainStats,
    },
    // schema 5+
    navigation: {
      current_major: state.currentMajor,
      current_sub_step: state.currentSubStep,
      step_status: state.stepStatus,
    },
    // schema 5+
    ui: {
      table_sorting: state.tableSorting,
    },
    // schema 5+. lib/sourceFingerprint.ts. 복원 측이 현재 파일과 대조해
    // loadSequence/loadEvolveproCsv 재도출 필요 여부를 정한다.
    sources: {
      sequence_fingerprint: extras.sequenceFingerprint,
      evolvepro_csv_fingerprint: extras.evolveproCsvFingerprint,
    },
  };
}

// ─── 복원 측이 같이 읽어야 하는 그룹 ─────────────────────────────────────
//
// 위 `results` 객체 리터럴은 designResults/successCount/totalCount 를 조건 없이
// 한 번에 쓴다. 셋은 구성상 한 덩어리이고, 화면도 셋을 한 측정값으로 읽는다
// (ResultTable.tsx 의 "successCount/totalCount designed" 배지가 designResults
// 표 위에 붙고, DesignReportContent.tsx 가 같은 둘로 성공률을 계산한다).
// 그런데 복원 측이 필드마다 독립 if 로 읽으면 한쪽만 착지한 상태가 만들어진다.
// JSON.stringify 는 NaN/Infinity 를 null 로 쓰므로 `typeof === "number"` 가
// 깨지고, 카운트만 초기값 0 으로 남아 세 줄짜리 표 위에 "0/0 designed" 가
// 뜬다. 그래서 판정을 여기, 쓰는 쪽 옆에 둔다. 읽는 쪽이 같은 튜플을 손으로
// 다시 적으면 그 순간부터 다시 어긋난다.

/** designResults 와 그 카운트. 스냅샷에서 통째로 읽거나 통째로 버린다. */
export interface KuroDesignOutcome {
  designResults: AppState["designResults"];
  successCount: number;
  totalCount: number;
}

export type GroupRead<T> =
  | { ok: true; value: T }
  | { ok: false; missing: string[] };

/** 저장된 카운트로 인정되는 값. JSON 왕복으로 null 이 된 NaN/Infinity 를 뺀다. */
function isRestorableCount(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/**
 * `results` 블록에서 설계 결과 그룹을 통째로 읽는다.
 *
 * 셋 중 하나라도 없거나 유한한 카운트가 아니면 그룹 전체를 거절하고 무엇이
 * 빠졌는지 돌려준다. 부분 적용을 도달 불가능하게 만드는 것이 목적이므로
 * "있는 것만 넣는" 완화 경로는 두지 않는다.
 */
export function readKuroDesignOutcome(results: unknown): GroupRead<KuroDesignOutcome> {
  const record =
    results !== null && typeof results === "object"
      ? (results as Record<string, unknown>)
      : {};
  const missing: string[] = [];
  if (!Array.isArray(record.designResults)) missing.push("designResults");
  if (!isRestorableCount(record.successCount)) missing.push("successCount");
  if (!isRestorableCount(record.totalCount)) missing.push("totalCount");
  if (missing.length > 0) return { ok: false, missing };
  return {
    ok: true,
    value: {
      designResults: record.designResults as AppState["designResults"],
      successCount: record.successCount as number,
      totalCount: record.totalCount as number,
    },
  };
}

/**
 * BenchmarkResult 의 필수 지표. `types/models.ts` 의 인터페이스와 1:1 이며
 * `n_trials` 만 optional 이라 여기서 빠져 있다(있으면 유한해야 한다).
 *
 * 복원 측이 이 블록을 컨테이너로만 검사하면 비유한 지표가 null 로 왕복해
 * `number` 자리에 앉고 화면에는 0.0% 로 찍힌다. 지표 하나가 무효면 그 항목은
 * 측정값이 아니므로 블록 전체를 쓰지 않는다. 재설계로 다시 만들 수 있는
 * 캐시라(위 saveCache 주석) 버리는 쪽이 틀린 숫자를 보여주는 쪽보다 싸다.
 */
const BENCHMARK_REQUIRED_METRICS = [
  "n_selected",
  "hit_rate",
  "mean_fitness",
  "unique_positions",
  "position_coverage",
  "domain_coverage",
  "structural_spread",
  "hits",
  "threshold",
] as const;

/** 스냅샷의 benchmarkResults 를 항목 단위로 검사한다. 무효 항목 키를 돌려준다. */
export function readKuroBenchmarkResults(
  value: unknown,
): GroupRead<AppState["benchmarkResults"]> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return { ok: false, missing: ["benchmarkResults"] };
  }
  const invalid: string[] = [];
  for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      invalid.push(key);
      continue;
    }
    const metrics = entry as Record<string, unknown>;
    const broken = BENCHMARK_REQUIRED_METRICS.some(
      (name) => typeof metrics[name] !== "number" || !Number.isFinite(metrics[name] as number),
    );
    const trialsBroken =
      metrics.n_trials !== undefined &&
      (typeof metrics.n_trials !== "number" || !Number.isFinite(metrics.n_trials));
    if (broken || trialsBroken) invalid.push(key);
  }
  if (invalid.length > 0) return { ok: false, missing: invalid };
  return { ok: true, value: value as AppState["benchmarkResults"] };
}
