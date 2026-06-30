/**
 * ActivityStepView, "activity" mame phase 단일 Step 3 화면.
 *
 * [source: spec §D2.4, mame StepView 신규]
 * [updated: spec Phase F F6, WizardContainer 적용]
 * [updated: spec Phase G #19, activity.export 폐지, activity.mergeExport로 통합 (2-step)]
 * [updated: PR2b, activity.ingest/mergeExport 단일 Step 3로 통합 (raw 리포트 수용 흐름)]
 *
 * 단일 sub-step(activity.ingest) 화면에 ingest → merge → export → build를 한 번에
 * 쌓아 보여준다. activity.mergeExport는 redirect/migration용 legacy id로 남아 같은
 * 화면을 렌더한다.
 *   IngestSection           → CSV/Excel 업로드 + WT 어노테이션 (flat-CSV 경로)
 *   MergeSection            → genotype merge + replicate priority merge
 *   ExportSection           → EVOLVEpro xlsx 저장 + round handoff
 *   BuildEvolveproInputPanel → raw 리포트(라운드1) + 변이라벨 재측정 직접 입력 흐름
 *
 * ActivityPanel은 wrapper로 유지되므로 테스트 호환성 유지.
 */

import { useEffect } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { IngestSection, MergeSection, ExportSection } from "@/components/mame/panels/ActivityPanel";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { StepRedirectFallback } from "./StepRedirectFallback";
import { BuildEvolveproInputPanel } from "@/components/mame/panels/BuildEvolveproInputPanel";

export function ActivityStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);

  // Auto-create a round if none exists (mirrors ActivityPanel behavior)
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const addRound = useRoundStore((s) => s.addRound);
  useEffect(() => {
    if (activeRoundId === null) {
      addRound({ plate_meta: { plates: [] } });
    }
  }, [activeRoundId, addRound]);

  // activity는 단일 Step 3. activity.mergeExport는 legacy redirect id로 같은 화면을
  // 렌더하고, 그 외 sub-step이 흘러들면 activity.ingest로 보정한다.
  if (
    subStep !== "activity.ingest" &&
    subStep !== "activity.mergeExport"
  ) {
    return (
      <StepRedirectFallback
        currentSub={subStep}
        expectedFor="activity"
        setSubStep={setMameSubStep}
      />
    );
  }

  return (
    <WizardContainer
      stepIndex={1}
      stepTotal={1}
      stepLabel="3.1"
      progressLabel="3.1"
      titleKey="phaseC.mameSubSteps.activity.ingest"
      descriptionKey="phaseE.mameDescriptions.activity.ingest"
      onPrev={goToPrevStep}
    >
      <div className="space-y-6">
        <IngestSection />
        <MergeSection />
        <ExportSection />
        <BuildEvolveproInputPanel />
      </div>
    </WizardContainer>
  );
}
