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
import { buildKuroSnapshot } from "@/lib/kuroSnapshot";
import type { AppState } from "@/store/types";

// ─── 자동 저장 대상 셀렉터 ────────────────────────────────────────────────

/**
 * 자동 저장을 트리거할 상태 슬라이스.
 * 결과물 필드(designResults 등)는 의도적으로 제외한다.
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
    // diversity
    s.uniprotAccession,
    s.pipelineMode,
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
  ] as const;
}

// ─── 훅 ──────────────────────────────────────────────────────────────────

/**
 * Kuro 자동 저장 구독을 등록한다.
 * - scratch 프로젝트 또는 projectPath가 없으면 silent skip.
 * - 컴포넌트 언마운트(project 변경 포함) 시 구독 해제.
 */
export function useKuroAutosave(): void {
  const project = useKumaProject();
  // project 객체 자체가 매 렌더마다 새로 생성될 수 있으므로
  // path / scratch만 의존성으로 사용한다.
  const projectPath = project?.path ?? null;
  const scratch = project?.scratch ?? true;

  // target ref: subscribe 콜백 안에서 항상 최신 target을 참조하도록 보관
  const targetRef = useRef<AutosaveTarget>({ projectPath, scratch });
  targetRef.current = { projectPath, scratch };

  useEffect(() => {
    if (scratch || projectPath === null) return;

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
        () => buildKuroSnapshot(useAppStore.getState()),
      );
    });

    return unsubscribe;
  }, [projectPath, scratch]);
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
  });
  targetRef.current = {
    projectPath: project?.path ?? null,
    scratch: project?.scratch ?? true,
  };

  return async () => {
    await flushAutosave(targetRef.current, "kuro");
  };
}
