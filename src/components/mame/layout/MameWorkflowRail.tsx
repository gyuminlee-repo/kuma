/**
 * MameWorkflowRail — MAME 전용 WorkflowRail 래퍼.
 *
 * 7 sub-step을 MAME_SUBSTEP_ORDER 순서로 나열하고, 현재 sub-step 기준으로
 * progress %(14, 28, 42, 56, 70, 84, 100)와 step 상태(done/active/lock)를 계산한다.
 *
 * [source: v5-strategy.md §3 Sidebar (WorkflowRail)]
 * [source: v5-audit.md Phase 5 MAME 7화면 contract matrix]
 */

import { useTranslation } from "react-i18next";
import { WorkflowRail, type WorkflowStep } from "@/components/widgets/WorkflowRail";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";

const ALL_SUBSTEPS: MameSubStepId[] = [
  "setup.files",
  "setup.design",
  "analyze.inputs",
  "analyze.verdict",
  "analyze.plate",
  "activity.ingest",
  "activity.mergeExport",
];

const STEP_TOTAL = ALL_SUBSTEPS.length; // 7

/** 각 sub-step의 i18n 레이블 키 */
const STEP_LABEL_KEYS: Record<MameSubStepId, string> = {
  "setup.files": "phaseC.mameSubSteps.setup.files",
  "setup.design": "phaseC.mameSubSteps.setup.design",
  "analyze.inputs": "phaseC.mameSubSteps.analyze.inputs",
  "analyze.verdict": "phaseC.mameSubSteps.analyze.verdict",
  "analyze.plate": "phaseC.mameSubSteps.analyze.plate",
  "activity.ingest": "phaseC.mameSubSteps.activity.ingest",
  "activity.mergeExport": "phaseC.mameSubSteps.activity.mergeExport",
};

function computeProgress(activeIndex: number): number {
  // index 0 → 14%, index 6 → 100%
  return Math.round(((activeIndex + 1) / STEP_TOTAL) * 100);
}

export function MameWorkflowRail() {
  const { t } = useTranslation();
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);

  const activeIndex = ALL_SUBSTEPS.indexOf(currentSubStep);
  const progressPercent = computeProgress(Math.max(0, activeIndex));

  const steps: WorkflowStep[] = ALL_SUBSTEPS.map((id, idx) => {
    let state: WorkflowStep["state"];
    if (idx < activeIndex) {
      state = "done";
    } else if (idx === activeIndex) {
      state = "active";
    } else {
      state = "default";
    }

    return {
      num: idx + 1,
      title: t(STEP_LABEL_KEYS[id]),
      state,
      mini: idx === activeIndex ? "now" : idx === activeIndex + 1 ? "next" : undefined,
    };
  });

  return (
    <WorkflowRail
      title={t("mame.setup.files.railTitle")}
      progressPercent={progressPercent}
      steps={steps}
      onStepClick={(idx) => {
        const targetId = ALL_SUBSTEPS[idx];
        if (targetId) setMameSubStep(targetId);
      }}
      sideCard={
        activeIndex >= 0
          ? {
              title: t(STEP_LABEL_KEYS[ALL_SUBSTEPS[activeIndex]]),
              body: `${activeIndex + 1} / ${STEP_TOTAL}`,
            }
          : undefined
      }
    />
  );
}
