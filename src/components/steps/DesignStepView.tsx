/**
 * DesignStepView — "design" major step sub-step 디스패처.
 *
 * [source: spec §4.1 — DesignStepView (D2.1)]
 * [source: spec Phase E — E2 WizardContainer, E3 SequenceViewer hoist]
 * [source: spec Phase G — 4 sub-step 재배치 (#2)]
 * [source: 260514_kuma_patch_UI수정_스펙.md — Phase B (B1/B3/B6)]
 *
 * Sub-step 매핑 (Phase G):
 *   design.load     → SequenceInput (파일 로드)
 *   design.mutation → MutationInput
 *   design.params   → ParameterPanel
 *   design.submit   → DesignSummaryCard + DiversityOptions + RunDesignActionView
 *
 * NOTE (Phase G #7): UniprotSearch 는 DiversitySections (line 159) 안에서만 마운트됨.
 * SequenceViewer 는 AppLayout main slot 상단으로 호이스팅 (E3).
 */

import { useAppStore } from "@/store/appStore";
import { SequenceInput } from "@/components/panels/InputPanel/SequenceInput";
import { DiversityOptions } from "@/components/panels/InputPanel/DiversityOptions";
import { MutationInput } from "@/components/panels/InputPanel/MutationInput";
import { ParameterPanel } from "@/components/panels/ParameterPanel";
import { RunDesignActionView } from "./RunDesignAction";
import { WizardContainer } from "./WizardContainer";
import { DesignSummaryCard } from "./DesignSummaryCard";
import { KURO_STEP_INDEX, TOTAL_KURO_STEPS } from "./constants";
import { validateForNext, type KuroSubStepId } from "@/store/validation";
import { useRunDesign } from "@/hooks/useRunDesign";

function SubmitDesignStep({ onPrev }: { onPrev: () => void }) {
  const runDesign = useRunDesign();
  const evolveproMode = useAppStore((s) => s.evolveproMode);
  const showPoolFilters = evolveproMode !== "topN";

  return (
    <WizardContainer
      stepIndex={KURO_STEP_INDEX["design.submit"]}
      stepTotal={TOTAL_KURO_STEPS}
      titleKey="phaseC.subSteps.design.submit"
      descriptionKey="phaseE.descriptions.design.submit"
      onPrev={onPrev}
      onNext={runDesign.run}
      nextLabelKey="phaseC.run.primary"
      isValid={() => !runDesign.isDesigning && !runDesign.hasBlockingIssue}
    >
      {/* Phase B6 (#1,#15): 직전 step 변경값을 카드로 한눈에 — stale 인상 제거 */}
      <DesignSummaryCard />
      {/* UniprotSearch は DiversityOptions → DiversitySections 内で自動マウント (Phase G #7) */}
      {showPoolFilters && <DiversityOptions />}
      <RunDesignActionView controller={runDesign} />
    </WizardContainer>
  );
}

export function DesignStepView() {
  const subStep = useAppStore((s) => s.currentSubStep);
  const goToNextStep = useAppStore((s) => s.goToNextStep);
  const goToPrevStep = useAppStore((s) => s.goToPrevStep);

  switch (subStep) {
    case "design.load":
      return (
        <WizardContainer
          stepIndex={KURO_STEP_INDEX["design.load"]}
          stepTotal={TOTAL_KURO_STEPS}
          titleKey="phaseC.subSteps.design.load"
          descriptionKey="phaseE.descriptions.design.load"
          onNext={() => goToNextStep()}
          onPrev={undefined}
          validateBeforeNext={() =>
            validateForNext("design.load" as KuroSubStepId, useAppStore.getState())
          }
        >
          <SequenceInput />
        </WizardContainer>
      );
    case "design.mutation":
      return (
        <WizardContainer
          stepIndex={KURO_STEP_INDEX["design.mutation"]}
          stepTotal={TOTAL_KURO_STEPS}
          titleKey="phaseC.subSteps.design.mutation"
          descriptionKey="phaseE.descriptions.design.mutation"
          onNext={() => goToNextStep()}
          onPrev={() => goToPrevStep()}
          validateBeforeNext={() =>
            validateForNext("design.mutation" as KuroSubStepId, useAppStore.getState())
          }
        >
          <MutationInput />
        </WizardContainer>
      );
    case "design.params":
      return (
        <WizardContainer
          stepIndex={KURO_STEP_INDEX["design.params"]}
          stepTotal={TOTAL_KURO_STEPS}
          titleKey="phaseC.subSteps.design.params"
          descriptionKey="phaseE.descriptions.design.params"
          onNext={() => goToNextStep()}
          onPrev={() => goToPrevStep()}
          validateBeforeNext={() =>
            validateForNext("design.params" as KuroSubStepId, useAppStore.getState())
          }
        >
          <ParameterPanel />
        </WizardContainer>
      );
    case "design.submit":
      return (
        <SubmitDesignStep onPrev={() => goToPrevStep()} />
      );
    default:
      return null;
  }
}
