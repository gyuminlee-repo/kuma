/**
 * useKuroAutosave.ts — Phase 2: Kuro store 자동 저장 구독 훅
 *
 * 1. 자동 저장 대상 필드가 변경되면 scheduleAutosave 호출 (1.5초 디바운스)
 * 2. 탭 전환, Run Design, 윈도우 close 직전에 flushAutosave 호출
 */

import { useEffect, useRef } from "react";
import { shallow } from "zustand/shallow";
import { useAppStore } from "@/store/appStore";
import { useKumaProject } from "@/state/projectContext";
import { scheduleAutosave, flushAutosave, type AutosaveTarget } from "@/lib/autosave";
import { registerShutdownHook } from "@/lib/shutdownHook";
import { buildKuroSnapshot, type KuroSnapshotExtras } from "@/lib/kuroSnapshot";
import { fingerprintSource, type SourceFingerprint } from "@/lib/sourceFingerprint";
import type { AppState } from "@/store/types";

// ─── 자동 저장 대상 셀렉터 ────────────────────────────────────────────────

/**
 * 자동 저장을 트리거할 상태 슬라이스.
 * schema 2부터 결과물 필드(designResults 등)도 포함해 앱 재시작 후
 * 디자인 결과까지 그대로 이어서 작업할 수 있게 한다.
 *
 * schema 5에서 화면 위치·EVOLVEpro 파생 상태·도메인/구조·설정·결과 부속을
 * 추가했지만, 전부를 이 셀렉터에 넣지는 않는다. 아래 항목은 값은 스냅샷에
 * 싣되(buildKuroSnapshot이 useAppStore.getState()에서 직접 읽는다) 이 셀렉터의
 * 트리거 목록에서는 뺐다. 이유는 두 가지다.
 *
 * 1. `seqInfo`는 loadSequence 응답 JSON 전체라 매 로드마다 새 참조가 되는 건
 *    맞지만, 그 시점엔 fastaPath도 함께 바뀌므로 fastaPath가 이미 같은 변경을
 *    감지한다. seqInfo를 추가로 넣으면 참조 동일성 비교만 중복될 뿐 새로운
 *    트리거 시점을 만들지 않는다.
 * 2. `evolveproRankedCandidates`/`yPredMap`/`domainStats`는 loadEvolveproCsv
 *    응답에서 나오는데, 그 트리거 시점은 이미 evolveproCsvPath 변경(또는 그
 *    결과인 mutationText 변경)으로 잡힌다. 이 값들을 셀렉터에 넣으면 매 로드마다
 *    새 객체/배열 참조가 생겨 shallow 비교가 깨지는 것은 같지만, 트리거해야 할
 *    시점을 이미 다른 필드가 커버하고 있어 추가 이득이 없다. 반대로 값이 커서
 *    (evolveproRankedCandidates·yPredMap은 pool 크기에 비례) 매 변경마다 이
 *    배열 전체를 shallow 비교 대상에 얹으면 diff 비용만 늘어난다.
 *
 * `currentSubStep`/`currentMajor`처럼 사용자가 화면을 옮길 때마다 바뀌는
 * 값은 안정적인 문자열 리터럴이라(객체가 아님) shallow 비교가 깨지는 비용이
 * 낮고, 화면 위치를 잃지 않는 것이 사용자에게 보이는 이득이라 트리거 목록에
 * 넣는다. `stepStatus`는 매 markDone마다 새 객체가 되지만 호출 빈도가 낮아
 * (사용자 진행 단계당 1회) 포함해도 저장 폭주로 이어지지 않는다.
 *
 * `uniprotCandidates`는 위 2번과 반대로 셀렉터에 넣는다. loadSequence/
 * setSelectedGene이 fire-and-forget으로 띄우는 searchUniprot 완료 시 딱 한
 * 번 새 배열로 바뀌고, 그 뒤로는 사용자가 다시 검색을 트리거하지 않는 한
 * 안정 참조로 남는다(evolveproRankedCandidates처럼 매 CSV 로드마다 반복
 * 갈아치워지는 값이 아니다). 검색 결과 자체가 저장 대상 상태 변화이므로
 * 넣지 않으면 이 값만 자동 저장을 트리거하지 못해 다음 디바운스 주기까지
 * (또는 flush 시점까지) 최신 후보가 디스크에 반영되지 않는다.
 */
function kuroAutosaveSelector(s: AppState): readonly unknown[] {
  return [
    // input
    s.fastaPath,
    s.selectedGene,
    s.organism,
    s.mutationText,
    s.mutationInputMode,
    s.evolveproCsvPath,
    s.evolveproVariantColumn,
    s.evolveproScoreColumn,
    s.evolveproScoreOrder,
    s.evolveproSheetName,
    // diversity
    s.uniprotAccession,
    s.evolveproMode,
    s.domains,
    s.disabledDomains,
    s.positionDiversityEnabled,
    s.maxPerPosition,
    s.domainDiversityEnabled,
    s.domainStrategy,
    s.domainOverlapPolicy,
    s.linkerHandling,
    s.domainQuotaMin,
    s.paretoDiversityEnabled,
    s.entropyWeightEnabled,
    s.entropyWeight,
    s.paretoPoolMultiplier,
    s.distanceMode,
    s.evolveproRound,
    s.roundSize,
    s.autoRedesignOnLoad,
    s.saveCache,
    s.refDomainHash,
    s.structureAccession,
    s.structureLoaded,
    s.structuralDiversityEnabled,
    s.structuralKappa,
    // uniprotSearching은 넣지 않는다. "진행 중" 플래그를 트리거에 넣으면 검색
    // 시작·종료 두 시점 모두 저장을 유발하고, kuroSnapshot.ts가 애초에 그 값을
    // 스냅샷에 싣지 않으므로(재시작 후 영원히 도는 스피너 방지) 트리거로서도
    // 의미가 없다. uniprotCandidates만 넣는 이유는 위 docstring 참조.
    s.uniprotCandidates,
    // parameters
    s.selectedPolymerase,
    s.codonStrategy,
    s.maxPrimers,
    s.tmFwdTarget,
    s.tmRevTarget,
    s.tmOverlapTarget,
    s.gcMin,
    s.gcMax,
    s.primerLenEnabled,
    s.fwdLenMin,
    s.fwdLenMax,
    s.revLenMin,
    s.revLenMax,
    s.fillOnFailure,
    s.overlapMode,
    s.tmTolerance,
    s.randomSeed,
    // benchmark (schema 5+)
    s.benchmarkTopPercentile,
    s.benchmarkRandomTrials,
    s.benchmarkRandomSeed,
    // results (schema 2+)
    s.designResults,
    s.successCount,
    s.totalCount,
    s.failedMutations,
    s.plateMappings,
    s.dedupInfo,
    s.manuallySwapped,
    s.customCandidates,
    s.rescuedMutationDetails,
    // results extras (schema 5+)
    s.rescuedMutations,
    s.showBenchmark,
    // ui (schema 5+)
    s.tableSorting,
    // navigation (schema 5+). stepStatus/currentSubStep/currentMajor 포함
    // 근거는 위 함수 docstring 참조.
    s.currentMajor,
    s.currentSubStep,
    s.stepStatus,
  ] as const;
}

// ─── 훅 ──────────────────────────────────────────────────────────────────

/**
 * Kuro 자동 저장 구독을 등록한다.
 * - 프로젝트가 열려 있으면 프로젝트의 .autosave/kuro.json에 저장한다.
 * - scratch(프로젝트 없음)이면 앱 데이터 디렉토리의 고정 파일에 저장한다.
 * - 컴포넌트 언마운트(project 변경 포함) 시 구독 해제.
 */
export function useKuroAutosave(): void {
  const project = useKumaProject();
  // project 객체 자체가 매 렌더마다 새로 생성될 수 있으므로
  // path / scratch만 의존성으로 사용한다.
  const projectPath = project?.path ?? null;
  const scratch = project?.scratch ?? true;

  // target ref: subscribe 콜백 안에서 항상 최신 target을 참조하도록 보관
  const targetRef = useRef<AutosaveTarget>({ projectPath, scratch, scratchFallback: true });
  targetRef.current = { projectPath, scratch, scratchFallback: true };

  /**
   * 서열/EVOLVEpro CSV 파일 지문 캐시.
   *
   * scheduleAutosave의 buildSnapshot은 동기 함수라 stat()(비동기)을 그 안에서
   * 직접 부를 수 없다. 대신 fastaPath/evolveproCsvPath가 바뀔 때마다 별도
   * effect가 비동기로 다시 계산해 이 ref에 채워 두고, buildSnapshot은 이미
   * 계산된 값을 동기로 읽기만 한다.
   *
   * 인과 관계(경로 변경 → 지문 재계산 창 → 저장 시점 상충 시 무슨 일이
   * 일어나는가): 경로가 바뀌면 이 ref의 갱신은 위 recompute의 stat() 왕복이
   * 끝나야 완료되는데, 그 사이에도 kuroAutosaveSelector가 fastaPath/
   * evolveproCsvPath 변경 자체를 감지해 scheduleAutosave를 걸 수 있다. 이
   * 디바운스(1.5초)가 stat() 왕복보다 먼저 만료돼 스냅샷이 만들어지면,
   * fingerprintsRef에는 아직 새 파일의 지문이 아니라 옛 파일(또는 null)의
   * 지문이 남아 있어 스냅샷은 그 구 지문을 그대로 싣는다. 다음 재시작 때
   * 복원 측이 그 지문을 현재 파일과 대조하면 새 파일의 실제 지문과 달라 항상
   * 불일치로 판정되고, 그 결과는 loadSequence/loadEvolveproCsv 재도출
   * 폴백이다(applyKuroSnapshot의 fingerprintsEqual 분기). 즉 최악의 경우도
   * "빠른 경로를 못 쓰고 평소처럼 재도출한다"이며, 잘못된 지문이 잘못된
   * 파일을 정본으로 착지시키는 데이터 손실 경로는 없다(지문 불일치는 항상
   * 안전한 쪽인 재도출로 떨어진다).
   */
  const fingerprintsRef = useRef<{
    sequence: SourceFingerprint | null;
    evolveproCsv: SourceFingerprint | null;
  }>({ sequence: null, evolveproCsv: null });

  useEffect(() => {
    let cancelled = false;
    const recompute = async (fastaPath: string, evolveproCsvPath: string): Promise<void> => {
      const [sequence, evolveproCsv] = await Promise.all([
        fingerprintSource(fastaPath),
        fingerprintSource(evolveproCsvPath),
      ]);
      if (cancelled) return;
      fingerprintsRef.current = { sequence, evolveproCsv };
    };

    const initial = useAppStore.getState();
    let prevFasta = initial.fastaPath;
    let prevCsv = initial.evolveproCsvPath;
    void recompute(prevFasta, prevCsv);

    const unsubscribe = useAppStore.subscribe((state) => {
      if (state.fastaPath === prevFasta && state.evolveproCsvPath === prevCsv) return;
      prevFasta = state.fastaPath;
      prevCsv = state.evolveproCsvPath;
      void recompute(prevFasta, prevCsv);
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    // subscribeWithSelector 없이도 동작하도록 일반 subscribe 사용.
    // slice selector + shallow 비교로 불필요한 flush를 방지한다.
    let prev = kuroAutosaveSelector(useAppStore.getState());

    const unsubscribe = useAppStore.subscribe((state) => {
      const next = kuroAutosaveSelector(state);
      if (shallow(prev, next)) return;
      prev = next;
      scheduleAutosave(
        targetRef.current,
        "kuro",
        // 경로 상대화 기준은 쓰기 시점의 대상 프로젝트다. targetRef를 따라가야
        // 프로젝트 전환 직후 예약분이 옛 폴더 기준으로 상대화되지 않는다.
        () => {
          const extras: KuroSnapshotExtras = {
            sequenceFingerprint: fingerprintsRef.current.sequence,
            evolveproCsvFingerprint: fingerprintsRef.current.evolveproCsv,
          };
          return buildKuroSnapshot(
            useAppStore.getState(),
            targetRef.current.scratch ? null : targetRef.current.projectPath,
            extras,
          );
        },
      );
    });

    return unsubscribe;
  }, [projectPath, scratch]);

  // Round 상태(rounds/active_round_id)는 이 훅에서 트리거하지 않는다. KURO
  // 스냅샷이 Round 엔티티를 저장하지 않기 때문이다(lib/kuroSnapshot.ts 헤더
  // 참조, MAME 스냅샷 단독 소유, useMameAutosave.ts가 이미 useRoundStore를
  // 구독해 트리거한다).

  // 종료 직전 강제 저장. 디바운스가 1.5초라 이것이 없으면 마지막 편집분이
  // 통째로 날아간다. 훅 등록을 이 훅 안에 두는 이유는 호출부가 반환된 flush
  // 함수를 쓰지 않아도(현재 MainShell이 그렇다) 보장되게 하기 위해서다.
  useEffect(() => {
    return registerShutdownHook(async () => {
      await flushAutosave(targetRef.current, "kuro");
    });
  }, []);
}

/**
 * Run Design 시작 직전에 호출한다 (입력 보존).
 * 콜백을 반환하므로 onClick handler에서 await 가능.
 */
export function useFlushKuroBeforeDesign(): () => Promise<void> {
  const project = useKumaProject();
  const targetRef = useRef<AutosaveTarget>({
    projectPath: project?.path ?? null,
    scratch: project?.scratch ?? true,
    scratchFallback: true,
  });
  targetRef.current = {
    projectPath: project?.path ?? null,
    scratch: project?.scratch ?? true,
    scratchFallback: true,
  };

  return async () => {
    await flushAutosave(targetRef.current, "kuro");
  };
}
