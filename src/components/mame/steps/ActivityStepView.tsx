/**
 * ActivityStepView, "activity" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4, mame StepView 신규]
 * [updated: spec Phase F F6, WizardContainer 적용]
 * [updated: spec Phase G #19, activity.export 폐지, activity.mergeExport로 통합 (2-step)]
 * [updated: Activity 단일 step 통합, ingest + merge + export 를 한 화면에서 처리 (1-step)]
 * [updated: Activity 단일 측정값 파이프라인. route 선택기는 제거되고
 *    BuildEvolveproInputPanel 의 측정값 형식 선택 하나만 남는다. NGS verdict 는
 *    모든 형식에서 필수다.]
 * [updated: Activity UX 재설계, 2-step으로 분리:
 *    activity.ingest  = EVOLVEpro-input 생성 (활성값 소스 선택)
 *    activity.signals = cross-round classification (AdvisoryDecisionCard)]
 * [updated: RoundHandoffButton 마운트 제거. 그 버튼의 활성 조건은
 *    merged_table.length > 0 인데 그것을 채우던 MergeSection 이 ac0229c6
 *    (v0.15.12) 에서 삭제돼, 남은 writer 는 manifest 재실행이 부르는
 *    activitySlice.mergeForEvolvepro(src/lib/reRun.ts) 뿐이다. 정상 흐름에서는
 *    영구 disabled 였고 tooltip 은 이미 없는 UI 를 쓰라고 안내했다.
 *    handoffNextRound/loadRoundActivity 는 지우지 않는다.]
 * [updated: Janus 장비 설정이 step 3 으로 분리되면서 Activity 는 step 4 가 됐다.
 *    표기는 4.1 / 4.2, sub-step id 는 그대로다.]
 *
 * Sub-step:
 *   activity.ingest    → BuildEvolveproInputPanel
 *   activity.signals   → AdvisoryDecisionCard
 *   activity.mergeExport → legacy id, redirects to activity.ingest
 *
 */

import { useEffect } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { StepRedirectFallback } from "./StepRedirectFallback";
import { BuildEvolveproInputPanel } from "@/components/mame/panels/BuildEvolveproInputPanel";
import { AdvisoryDecisionCard } from "@/components/round/AdvisoryDecisionCard";
import { useKumaProject } from "@/state/projectContext";
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
    label: "4.1",
    progressLabel: `4.1 / ${ACTIVITY_TOTAL}`,
    titleKey: "phaseC.mameSubSteps.activity.ingest",
    descriptionKey: "phaseE.mameDescriptions.activity.ingest",
  },
  "activity.signals": {
    index: 2,
    label: "4.2",
    progressLabel: `4.2 / ${ACTIVITY_TOTAL}`,
    titleKey: "phaseC.mameSubSteps.activity.signals",
    descriptionKey: "phaseE.mameDescriptions.activity.signals",
  },
};

function ActivityIngestStep() {
  return <BuildEvolveproInputPanel />;
}

function ActivitySignalsStep() {
  return (
    <div className="space-y-6">
      <AdvisoryDecisionCard />
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
  const project = useKumaProject();

  // Auto-create a round if none exists (mirrors ActivityPanel behavior)
  const activeRoundId = useRoundStore((s) => s.active_round_id);
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

  function selectedActivityRouteIsComplete(): boolean {
    return hasCompletedBuildEvolveproOutput(
      loadBuildEvolveproFromStorage(project?.path),
      buildEvolveproCompletion,
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
        <ActivityIngestStep />
      ) : (
        <ActivitySignalsStep />
      )}
    </WizardContainer>
  );
}
