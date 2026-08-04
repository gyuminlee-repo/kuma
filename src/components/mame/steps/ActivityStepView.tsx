/**
 * ActivityStepView, "activity" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4, mame StepView 신규]
 * [updated: spec Phase F F6, WizardContainer 적용]
 * [updated: spec Phase G #19, activity.export 폐지, activity.mergeExport로 통합 (2-step)]
 * [updated: Activity 단일 step 통합, ingest + merge + export 를 한 화면에서 처리 (1-step)]
 * [updated: v0.15.6, 두 EVOLVEpro-input 경로를 하나로 통합. 경로 선택기 대신
 *    활성값 소스 축(ActivitySourceSelector)만 남고, NGS 는 어느 소스에서도
 *    빠지지 않는다: upload 소스는 MergeSection 의 genotype join, plate-layout
 *    소스는 BuildEvolveproInputPanel 의 verdict 파일 gating 으로 들어간다.]
 * [updated: Step 3 UX 재설계, 2-step으로 분리:
 *    3.1 (activity.ingest)  = EVOLVEpro-input 생성 (활성값 소스 선택)
 *    3.2 (activity.signals) = cross-round classification (AdvisoryDecisionCard) + round handoff]
 *
 * Sub-step:
 *   activity.ingest    → ActivitySourceSelector + (IngestSection/MergeSection/ExportSection | BuildEvolveproInputPanel)
 *   activity.signals   → AdvisoryDecisionCard + RoundHandoffButton
 *   activity.mergeExport → legacy id, redirects to activity.ingest
 *
 * ActivityPanel.tsx는 세 섹션(Ingest/Merge/Export)만 export한다. 도달 불가였던
 * ActivityPanel 래퍼는 제거됐다.
 */

import { useEffect, useState } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import { IngestSection, MergeSection, ExportSection } from "@/components/mame/panels/ActivityPanel";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { StepRedirectFallback } from "./StepRedirectFallback";
import { BuildEvolveproInputPanel } from "@/components/mame/panels/BuildEvolveproInputPanel";
import { ActivitySourceSelector } from "@/components/mame/panels/ActivitySourceSelector";
import { AdvisoryDecisionCard } from "@/components/round/AdvisoryDecisionCard";
import { RoundHandoffButton } from "@/components/round/RoundHandoffButton";
import {
  loadActivityRouteFromStorage,
  saveActivityRouteToStorage,
  type ActivityRoute,
} from "@/lib/mame/activityRouteStorage";
import {
  hasCompletedBuildEvolveproOutput,
  loadBuildEvolveproFromStorage,
} from "@/lib/mame/buildEvolveproFormStorage";

const ACTIVITY_TOTAL = 2;

const STEP_CONFIG: Record<
  "activity.ingest" | "activity.signals",
  {
    index: number;
    label: string;
    progressLabel: string;
    titleKey: string;
    descriptionKey: string;
  }
> = {
  "activity.ingest": {
    index: 1,
    label: "3.1",
    progressLabel: `3.1 / ${ACTIVITY_TOTAL}`,
    titleKey: "phaseC.mameSubSteps.activity.ingest",
    descriptionKey: "phaseE.mameDescriptions.activity.ingest",
  },
  "activity.signals": {
    index: 2,
    label: "3.2",
    progressLabel: `3.2 / ${ACTIVITY_TOTAL}`,
    titleKey: "phaseC.mameSubSteps.activity.signals",
    descriptionKey: "phaseE.mameDescriptions.activity.signals",
  },
};

function ActivityIngestStep({
  route,
  onRouteChange,
}: {
  route: ActivityRoute;
  onRouteChange: (route: ActivityRoute) => void;
}) {
  return (
    <div className="space-y-6">
      <ActivitySourceSelector value={route} onChange={onRouteChange} />
      {route === "genotype" ? (
        <>
          <IngestSection />
          <MergeSection />
          <ExportSection />
        </>
      ) : (
        <BuildEvolveproInputPanel />
      )}
    </div>
  );
}

function ActivitySignalsStep({ activeRoundId }: { activeRoundId: string | null }) {
  return (
    <div className="space-y-6">
      <AdvisoryDecisionCard />
      {activeRoundId && <RoundHandoffButton round_id={activeRoundId} />}
    </div>
  );
}

export function ActivityStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);
  const buildEvolveproCompletion = useMameAppStore(
    (s) => s.buildEvolveproCompletion,
  );
  const [route, setRoute] = useState<ActivityRoute>(() => loadActivityRouteFromStorage());

  // Auto-create a round if none exists (mirrors ActivityPanel behavior)
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const rounds = useRoundStore((s) => s.rounds);
  const addRound = useRoundStore((s) => s.addRound);
  useEffect(() => {
    if (activeRoundId === null) {
      addRound({ plate_meta: { plates: [] } });
    }
  }, [activeRoundId, addRound]);

  // Legacy activity.mergeExport id redirects to the first valid sub-step.
  if (subStep !== "activity.ingest" && subStep !== "activity.signals") {
    return (
      <StepRedirectFallback
        currentSub={subStep}
        expectedFor="activity"
        setSubStep={setMameSubStep}
      />
    );
  }

  const config = STEP_CONFIG[subStep];

  function goToSubStep(id: MameSubStepId) {
    setMameSubStep(id);
  }

  function handleRouteChange(next: ActivityRoute) {
    setRoute(next);
    saveActivityRouteToStorage(next);
  }

  function selectedActivityRouteIsComplete(): boolean {
    if (route === "plateLayout") {
      return hasCompletedBuildEvolveproOutput(
        loadBuildEvolveproFromStorage(),
        buildEvolveproCompletion,
      );
    }
    const activeRound = rounds.find((round) => round.id === activeRoundId);
    return Boolean(
      activeRound?.activity ||
        (activeRound?.merged_table && activeRound.merged_table.length > 0),
    );
  }

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={ACTIVITY_TOTAL}
      stepLabel={config.label}
      progressLabel={config.progressLabel}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      onPrev={subStep === "activity.signals" ? () => goToSubStep("activity.ingest") : goToPrevStep}
      onNext={subStep === "activity.ingest" ? () => goToSubStep("activity.signals") : undefined}
      validateBeforeNext={
        subStep === "activity.ingest"
          ? () =>
              selectedActivityRouteIsComplete()
                ? { ok: true }
                : {
                    ok: false,
                    missing: ["mame.activity.route.completeCurrentRoute"],
                  }
          : undefined
      }
    >
      {subStep === "activity.ingest" ? (
        <ActivityIngestStep route={route} onRouteChange={handleRouteChange} />
      ) : (
        <ActivitySignalsStep activeRoundId={activeRoundId} />
      )}
    </WizardContainer>
  );
}
