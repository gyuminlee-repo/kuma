/**
 * MameWorkflowRail — MAME 전용 WorkflowRail 래퍼.
 *
 * 6 sub-step(setup 1 + analyze 2 + janus 1 + activity 2)을 MAME_SUBSTEP_ORDER
 * 순서로 나열하고, 현재 sub-step 기준으로
 * progress %와 step 상태(done/active/lock)를 계산한다.
 *
 * [source: v5-strategy.md §3 Sidebar (WorkflowRail)]
 * [source: v5-audit.md Phase 5 MAME 7화면 contract matrix]
 */

import { useTranslation } from "react-i18next";
import { WorkflowRail, type WorkflowStep } from "@/components/widgets/WorkflowRail";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import type { MamePhase } from "@/store/mame/slices/phaseSlice";
import { isMameSubStepDone } from "@/lib/mame/mameStepCompletion";
import { loadBuildEvolveproFromStorage } from "@/lib/mame/buildEvolveproFormStorage";
import { useKumaProject } from "@/state/projectContext";

const ALL_SUBSTEPS: MameSubStepId[] = [
  "setup.files",
  "analyze.inputs",
  "analyze.review",
  "janus.settings",
  "activity.ingest",
  "activity.signals",
];

const STEP_TOTAL = ALL_SUBSTEPS.length; // 6

/** Major.Sub 표기 (spec §5.2). KURO는 단일 카운트, MAME는 Major.Sub.
 * Legacy analyze.verdict/plate retained as 2.2 alias for migration/redirect rendering.
 * Janus instrument settings took 3.1, so Activity moved to 4.x. */
const SUBSTEP_DISPLAY: Record<MameSubStepId, string> = {
  "setup.files": "1.1",
  "setup.design": "1.2",
  "analyze.inputs": "2.1",
  "analyze.review": "2.2",
  "analyze.verdict": "2.2",
  "analyze.plate": "2.2",
  "janus.settings": "3.1",
  "activity.ingest": "4.1",
  "activity.signals": "4.2",
  "activity.mergeExport": "4.2",
};

/** 각 sub-step이 속한 major group. */
const SUBSTEP_MAJOR: Record<MameSubStepId, MamePhase> = {
  "setup.files": "setup",
  "setup.design": "setup",
  "analyze.inputs": "analyze",
  "analyze.review": "analyze",
  "analyze.verdict": "analyze",
  "analyze.plate": "analyze",
  "janus.settings": "janus",
  "activity.ingest": "activity",
  "activity.signals": "activity",
  "activity.mergeExport": "activity",
};

/** Major group labels reuse the existing `mame.appLayout.*Tab` strings (without the
 * leading "1. "/"2. "/"3. " prefix; the rail prepends its own numbering). */
const MAJOR_ORDER: Array<{ id: MamePhase; num: number; labelKey: string }> = [
  { id: "setup", num: 1, labelKey: "mame.appLayout.barcodeSetupTab" },
  { id: "analyze", num: 2, labelKey: "mame.appLayout.analyzeTab" },
  { id: "janus", num: 3, labelKey: "mame.appLayout.janusTab" },
  { id: "activity", num: 4, labelKey: "mame.appLayout.activityTab" },
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
  "activity.signals": "phaseC.mameSubSteps.activity.signals",
  "activity.mergeExport": "phaseC.mameSubSteps.activity.mergeExport",
  "janus.settings": "phaseC.mameSubSteps.janus.settings",
};

function computeProgress(activeIndex: number): number {
  // index 0 → 17%, index 5 → 100%
  return Math.round(((activeIndex + 1) / STEP_TOTAL) * 100);
}

function phaseOfSubStep(id: MameSubStepId): MamePhase {
  return SUBSTEP_MAJOR[id];
}

export function MameWorkflowRail() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMamePhase = useMameAppStore((s) => s.setMamePhase);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const inputDir = useMameAppStore((s) => s.inputDir);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const verdicts = useMameAppStore((s) => s.verdicts);
  const summary = useMameAppStore((s) => s.summary);
  const buildEvolveproCompletion = useMameAppStore(
    (s) => s.buildEvolveproCompletion,
  );
  const janusSettings = useMameAppStore((s) => s.janusSettings);
  const janusMappingAutosave = useMameAppStore((s) => s.janusMappingAutosave);
  const advisoryDecision = useMameAppStore((s) => s.advisoryDecision);
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const rounds = useRoundStore((s) => s.rounds);
  const activeRound = rounds.find((round) => round.id === activeRoundId);
  const activityComplete = Boolean(
    activeRound?.activity ||
      (activeRound?.merged_table && activeRound.merged_table.length > 0),
  );

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
      const done = isMameSubStepDone(id, {
        inputDir,
        expectedPath,
        referencePath,
        outputPath,
        verdicts,
        summary,
        activityComplete,
        buildEvolveproForm: loadBuildEvolveproFromStorage(project?.path),
        buildEvolveproCompletion,
        janusLiquidClass: janusSettings.liquidClass,
        janusMappingWritten: janusMappingAutosave?.status === "saved",
        advisoryDecision,
      });
      let state: WorkflowStep["state"];
      if (done) state = "done";
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
        if (!targetId) return;
        setMamePhase(phaseOfSubStep(targetId));
        setMameSubStep(targetId);
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
