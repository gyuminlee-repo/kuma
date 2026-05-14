/**
 * ActivityStepView — "activity" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 * [updated: spec Phase G #19 — activity.export 폐지, activity.mergeExport로 통합 (2-step)]
 *
 * Sub-step 매핑:
 *   activity.ingest      → IngestSection (CSV/Excel 업로드 + WT 어노테이션)
 *   activity.mergeExport → MergeExportSection (genotype merge + EVOLVEpro xlsx 저장 + round handoff)
 *
 * ActivityPanel은 wrapper로 유지되므로 테스트 호환성 유지.
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
  "activity.mergeExport": {
    index: 2,
    titleKey: "phaseC.mameSubSteps.activity.mergeExport",
    descriptionKey: "phaseE.mameDescriptions.activity.mergeExport",
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
    subStep !== "activity.mergeExport"
  ) {
    return null;
  }

  const config = STEP_CONFIG[subStep];
  const isLast = subStep === "activity.mergeExport";

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={2}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      onPrev={goToPrevStep}
      onNext={isLast ? undefined : goToNextStep}
    >
      <div className="space-y-6">
        {subStep === "activity.ingest" && <IngestSection />}
        {subStep === "activity.mergeExport" && (
          <>
            <MergeSection />
            <ExportSection />
          </>
        )}
      </div>
    </WizardContainer>
  );
}
