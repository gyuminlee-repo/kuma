/**
 * useMameAutosave.ts — mame store 자동 저장 구독 훅 (Phase 3)
 *
 * 호출 위치: MameAppLayout (mame 진입점 컴포넌트) 최상단.
 * 프로젝트가 scratch이거나 path가 null이면 silent skip.
 */

import { useCallback, useEffect, useRef } from "react";
import { useKumaProject } from "@/state/projectContext";
import { scheduleAutosave, flushAutosave, type AutosaveTarget } from "@/lib/autosave";
import { registerShutdownHook } from "@/lib/shutdownHook";
import { buildMameSnapshot } from "@/lib/mame/autosaveSnapshot";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";

function selectMameInputs(s: ReturnType<typeof useMameAppStore.getState>) {
  const r = s.rawRunParams;
  return [
    s.inputDir,
    s.expectedPath,
    s.referencePath,
    s.outputPath,
    s.selectedWells,
    s.wtPlacement,
    s.mode,
    s.ingestMode,
    s.inputMode,
    // rawRunParams — spread individual fields for change detection (object ref stays stable)
    r.customBarcodesPath,
    r.sequencingSummaryPath,
    r.mapqThreshold,
    s.cdsStart,
    s.cdsEnd,
    s.minFileSizeKb,
    s.minFilteredDepth,
    s.manyCutoff,
    s.maxConsensusNFraction,
    s.verdicts,
    s.replicates,
    s.summary,
    s.distributionStats,
    s.wells,
    s.selectedWell,
    s.runHealth,
    s.buildEvolveproCompletion,
    s.demuxResult,
    s.ampliconLengthEstimate,
    s.wellLayout,
    s.layoutProvenance,
    // The replicate axis a run was scored on. Watched here (not only written
    // with the verdicts) because a pooled or subset run is a fact about the
    // result that has to survive a restart, and clearing it is a change too.
    s.selectedNativeBarcodes,
    s.detectedBarcodeCount,
  ] as const;
}

function shallowEqualTuple(
  a: ReturnType<typeof selectMameInputs>,
  b: ReturnType<typeof selectMameInputs>,
): boolean {
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/**
 * mame store 입력 필드 변경 시 자동 저장을 스케줄한다.
 * Run Analysis 시작 직전 flush를 위한 `flushMameAutosave` 함수도 반환한다.
 */
export function useMameAutosave(): { flushMameAutosave: () => Promise<void> } {
  const project = useKumaProject();
  const targetRef = useRef<AutosaveTarget>({
    projectPath: project?.path ?? null,
    scratch: project?.scratch ?? true,
  });
  targetRef.current = {
    projectPath: project?.path ?? null,
    scratch: project?.scratch ?? true,
  };

  // Bridge the project root (from context) into the mame store so the analyze
  // slice can persist the result file (resultSnapshot.ts) without context
  // access. Scratch projects stash null -> no result file written.
  useEffect(() => {
    useMameAppStore.getState().setProjectPath(
      project && !project.scratch ? (project.path ?? null) : null,
    );
  }, [project?.path, project?.scratch]);

  useEffect(() => {
    if (!project || project.scratch || !project.path) return;

    const buildSnapshot = () => {
      const roundState = useRoundStore.getState();
      // 경로 상대화 기준은 쓰기 시점의 대상 프로젝트다. targetRef를 따라가야
      // 프로젝트 전환 직후 예약분이 옛 폴더 기준으로 상대화되지 않는다.
      return buildMameSnapshot(
        useMameAppStore.getState(),
        {
          rounds: roundState.rounds,
          activeRoundId: roundState.active_round_id,
        },
        targetRef.current.scratch ? null : targetRef.current.projectPath,
      );
    };
    const unsubscribe = useMameAppStore.subscribe(
      selectMameInputs,
      () => {
        scheduleAutosave(targetRef.current, "mame", buildSnapshot);
      },
      { equalityFn: shallowEqualTuple },
    );
    const unsubscribeRounds = useRoundStore.subscribe(() => {
      scheduleAutosave(targetRef.current, "mame", buildSnapshot);
    });

    return () => {
      unsubscribe();
      unsubscribeRounds();
    };
  }, [project?.path, project?.scratch]);

  const flushMameAutosave = useCallback(async (): Promise<void> => {
    await flushAutosave(targetRef.current, "mame");
  }, []);

  // kuro 쪽과 같은 이유로 종료 훅을 훅 내부에서 등록한다. 반환된
  // flushMameAutosave 를 호출부가 종료 경로에 연결하지 않아도 동작해야 한다.
  useEffect(() => {
    return registerShutdownHook(async () => {
      await flushAutosave(targetRef.current, "mame");
    });
  }, []);

  return { flushMameAutosave };
}
