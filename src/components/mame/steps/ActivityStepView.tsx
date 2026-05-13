/**
 * ActivityStepView — "activity" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 *
 * Sub-step 매핑:
 *   activity.ingest → IngestSection (CSV/Excel 업로드 + WT 어노테이션)
 *   activity.merge  → MergeSection (genotype merge + replicate priority)
 *   activity.export → ExportSection (EVOLVEpro xlsx 저장 + round handoff)
 *
 * ActivityPanel은 wrapper로 유지되므로 테스트 호환성 유지.
 * NOTE: D3.2 전까지 이 컴포넌트는 mount되지 않는다.
 */

import { useEffect } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { IngestSection, MergeSection, ExportSection } from "@/components/mame/panels/ActivityPanel";
import { WizardContainer } from "@/components/steps/WizardContainer";

const STEP_CONFIG = {
  "activity.ingest": {
    index: 1,
    titleKey: "phaseC.mameSubSteps.activity.ingest",
    descriptionKey: "phaseE.mameDescriptions.activity.ingest",
  },
  "activity.merge": {
    index: 2,
    titleKey: "phaseC.mameSubSteps.activity.merge",
    descriptionKey: "phaseE.mameDescriptions.activity.merge",
  },
  "activity.export": {
    index: 3,
    titleKey: "phaseC.mameSubSteps.activity.export",
    descriptionKey: "phaseE.mameDescriptions.activity.export",
  },
} as const;

export function ActivityStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);

  // Auto-create a round if none exists (mirrors ActivityPanel behavior)
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const addRound = useRoundStore((s) => s.addRound);
  useEffect(() => {
    if (activeRoundId === null) {
      addRound({ plate_meta: { plates: [] } });
    }
  }, [activeRoundId, addRound]);

  if (
    subStep !== "activity.ingest" &&
    subStep !== "activity.merge" &&
    subStep !== "activity.export"
  ) {
    return null;
  }

  const config = STEP_CONFIG[subStep];
  const isLast = subStep === "activity.export";

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={3}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      onPrev={goToPrevStep}
      onNext={isLast ? undefined : goToNextStep}
    >
      <div className="space-y-6">
        {subStep === "activity.ingest" && <IngestSection />}
        {subStep === "activity.merge" && <MergeSection />}
        {subStep === "activity.export" && <ExportSection />}
      </div>
    </WizardContainer>
  );
}
