/**
 * DesignStepView — "design" major step sub-step 디스패처.
 *
 * [source: spec §4.1 — DesignStepView (D2.1)]
 * [source: spec Phase E — E2 WizardContainer, E3 SequenceViewer hoist]
 * [source: spec Phase G — 4 sub-step 재배치 (#2)]
 *
 * Sub-step 매핑 (Phase G):
 *   design.load     → SequenceInput (파일 로드)
 *   design.mutation → MutationInput
 *   design.params   → ParameterPanel
 *   design.submit   → DiversityOptions (UniprotSearch 포함됨 via DiversitySections:159) + RunDesignAction
 *
 * NOTE (Phase G #7): UniprotSearch 직접 import/마운트 제거.
 *   UniprotSearch는 DiversitySections 안에서만 마운트됨 (DiversitySections.tsx line 159).
 *
 * SequenceViewer는 AppLayout main slot 상단으로 호이스팅 (E3).
 */

import { useAppStore } from "@/store/appStore";
import { SequenceInput } from "@/components/panels/InputPanel/SequenceInput";
import { DiversityOptions } from "@/components/panels/InputPanel/DiversityOptions";
import { MutationInput } from "@/components/panels/InputPanel/MutationInput";
import { ParameterPanel } from "@/components/panels/ParameterPanel";
import { RunDesignAction } from "./RunDesignAction";
import { WizardContainer } from "./WizardContainer";
import { KURO_STEP_INDEX, TOTAL_KURO_STEPS } from "./constants";

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
        >
          <ParameterPanel />
        </WizardContainer>
      );
    case "design.submit":
      return (
        <WizardContainer
          stepIndex={KURO_STEP_INDEX["design.submit"]}
          stepTotal={TOTAL_KURO_STEPS}
          titleKey="phaseC.subSteps.design.submit"
          descriptionKey="phaseE.descriptions.design.submit"
          onPrev={() => goToPrevStep()}
          nextLabelKey="phaseC.run.primary"
        >
          {/* UniprotSearch は DiversityOptions → DiversitySections 内で自動マウント (Phase G #7) */}
          <DiversityOptions />
          <RunDesignAction />
        </WizardContainer>
      );
    default:
      return null;
  }
}
