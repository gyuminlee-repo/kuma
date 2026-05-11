/**
 * useMameAutosave.ts — mame store 자동 저장 구독 훅 (Phase 3)
 *
 * 호출 위치: MameAppLayout (mame 진입점 컴포넌트) 최상단.
 * 프로젝트가 scratch이거나 path가 null이면 silent skip.
 */

import { useEffect } from "react";
import { useKumaProject } from "@/state/projectContext";
import { scheduleAutosave, flushAutosave, type AutosaveTarget } from "@/lib/autosave";
import { buildMameSnapshot } from "@/lib/mame/autosaveSnapshot";
import { useMameAppStore } from "@/store/mame/mameAppStore";

/** 자동 저장 대상 입력 필드 선택자. 결과물 필드는 제외. */
function selectMameInputs(s: ReturnType<typeof useMameAppStore.getState>) {
  const r = s.rawRunParams;
  return [
    s.inputDir,
    s.expectedPath,
    s.referencePath,
    s.outputPath,
    s.sampleMapPath,
    s.mode,
    s.ingestMode,
    s.inputMode,
    // rawRunParams — spread individual fields for change detection (object ref stays stable)
    r.customBarcodesPath,
    r.sequencingSummaryPath,
    r.minQscore,
    r.lengthMin,
    r.lengthMax,
    r.minBarcodeScore,
    r.targetLength,
    r.lengthToleranceBp,
    r.linkedTrim,
    r.revPrimerUniversal,
    r.normalizeHeaders,
    s.cdsStart,
    s.cdsEnd,
    s.minFileSizeKb,
    s.manyCutoff,
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

  useEffect(() => {
    if (!project || project.scratch || !project.path) return;

    const target: AutosaveTarget = { projectPath: project.path, scratch: project.scratch };

    const unsubscribe = useMameAppStore.subscribe(
      selectMameInputs,
      () => {
        scheduleAutosave(target, "mame", () =>
          buildMameSnapshot(useMameAppStore.getState()),
        );
      },
      { equalityFn: shallowEqualTuple },
    );

    return unsubscribe;
  }, [project?.path, project?.scratch]);

  const flushMameAutosave = async (): Promise<void> => {
    if (!project || project.scratch || !project.path) return;
    const target: AutosaveTarget = { projectPath: project.path, scratch: project.scratch };
    await flushAutosave(target, "mame");
  };

  return { flushMameAutosave };
}
