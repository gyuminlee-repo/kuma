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
  "analyze.review",
  "activity.ingest",
  "activity.mergeExport",
];

const STEP_TOTAL = ALL_SUBSTEPS.length; // 6

/** Major.Sub 표기 (spec §5.2). KURO는 단일 카운트, MAME는 Major.Sub.
 * Legacy analyze.verdict/plate retained as 2.2 alias for migration/redirect rendering. */
const SUBSTEP_DISPLAY: Record<MameSubStepId, string> = {
  "setup.files": "1.1",
  "setup.design": "1.2",
  "analyze.inputs": "2.1",
  "analyze.review": "2.2",
  "analyze.verdict": "2.2",
  "analyze.plate": "2.2",
  "activity.ingest": "3.1",
  "activity.mergeExport": "3.2",
};

/** 각 sub-step이 속한 major group. */
const SUBSTEP_MAJOR: Record<MameSubStepId, "setup" | "analyze" | "activity"> = {
  "setup.files": "setup",
  "setup.design": "setup",
  "analyze.inputs": "analyze",
  "analyze.review": "analyze",
  "analyze.verdict": "analyze",
  "analyze.plate": "analyze",
  "activity.ingest": "activity",
  "activity.mergeExport": "activity",
};

/** Major group labels reuse the existing `mame.appLayout.*Tab` strings (without the
 * leading "1. "/"2. "/"3. " prefix; the rail prepends its own numbering). */
const MAJOR_ORDER: Array<{ id: "setup" | "analyze" | "activity"; num: number; labelKey: string }> = [
  { id: "setup", num: 1, labelKey: "mame.appLayout.barcodeSetupTab" },
  { id: "analyze", num: 2, labelKey: "mame.appLayout.analyzeTab" },
  { id: "activity", num: 3, labelKey: "mame.appLayout.activityTab" },
];

/** Strip a leading numeric prefix like "1. " from translated major labels so the
 * rail can render its own `1.` prefix consistently across locales. */
function stripLeadingNumber(label: string): string {
  return label.replace(/^\s*\d+\.?\s*/, "");
}

/** 각 sub-step의 i18n 레이블 키 */
const STEP_LABEL_KEYS: Record<MameSubStepId, string> = {
  "setup.files": "phaseC.mameSubSteps.setup.files",
  "setup.design": "phaseC.mameSubSteps.setup.design",
  "analyze.inputs": "phaseC.mameSubSteps.analyze.inputs",
  "analyze.review": "phaseC.mameSubSteps.analyze.review",
  "analyze.verdict": "phaseC.mameSubSteps.analyze.review",
  "analyze.plate": "phaseC.mameSubSteps.analyze.review",
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

  // Build a heterogeneous list: [header, sub, sub, header, sub, sub, sub, ...]
  // Track the mapping rendered-index -> sub-step id so onStepClick navigates correctly.
  const steps: WorkflowStep[] = [];
  const renderedTargets: (MameSubStepId | null)[] = [];

  for (const major of MAJOR_ORDER) {
    steps.push({
      kind: "header",
      num: major.num,
      title: stripLeadingNumber(t(major.labelKey)),
      state: "default",
    });
    renderedTargets.push(null);

    const subs = ALL_SUBSTEPS.filter((id) => SUBSTEP_MAJOR[id] === major.id);
    for (const id of subs) {
      const idx = ALL_SUBSTEPS.indexOf(id);
      let state: WorkflowStep["state"];
      if (idx < activeIndex) state = "done";
      else if (idx === activeIndex) state = "active";
      else state = "default";

      steps.push({
        num: SUBSTEP_DISPLAY[id],
        title: t(STEP_LABEL_KEYS[id]),
        state,
        indent: true,
        mini: idx === activeIndex ? "now" : idx === activeIndex + 1 ? "next" : undefined,
      });
      renderedTargets.push(id);
    }
  }

  return (
    <WorkflowRail
      title={t("mame.setup.files.railTitle")}
      progressPercent={progressPercent}
      steps={steps}
      onStepClick={(renderedIdx) => {
        const targetId = renderedTargets[renderedIdx];
        if (targetId) setMameSubStep(targetId);
      }}
      sideCard={
        activeIndex >= 0
          ? {
              title: t(STEP_LABEL_KEYS[ALL_SUBSTEPS[activeIndex]]),
              body: `${SUBSTEP_DISPLAY[ALL_SUBSTEPS[activeIndex]]} / ${STEP_TOTAL}`,
            }
          : undefined
      }
    />
  );
}
