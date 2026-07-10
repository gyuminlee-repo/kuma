/**
 * ActivityStepView — "activity" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 * [updated: spec Phase G #19 — activity.export 폐지, activity.mergeExport로 통합 (2-step)]
 * [updated: Activity 단일 step 통합 — ingest + merge + export 를 한 화면에서 처리 (1-step)]
 *
 * Sub-step:
 *   activity.ingest → IngestSection + MergeSection + ExportSection + BuildEvolveproInputPanel
 *   activity.mergeExport → legacy id, activity.ingest 로 redirect
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

const ACTIVITY_TOTAL = 1;
const STEP_CONFIG = {
  index: 1,
  label: "3.1",
  progressLabel: `3.1 / ${ACTIVITY_TOTAL}`,
  titleKey: "phaseC.mameSubSteps.activity.ingest",
  descriptionKey: "phaseE.mameDescriptions.activity.ingest",
} as const;

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

  // Activity is a single merged step (ingest + merge + export). Any other id —
  // including the legacy activity.mergeExport — redirects here.
  if (subStep !== "activity.ingest") {
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
      stepIndex={STEP_CONFIG.index}
      stepTotal={ACTIVITY_TOTAL}
      stepLabel={STEP_CONFIG.label}
      progressLabel={STEP_CONFIG.progressLabel}
      titleKey={STEP_CONFIG.titleKey}
      descriptionKey={STEP_CONFIG.descriptionKey}
      onPrev={goToPrevStep}
      onNext={undefined}
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
