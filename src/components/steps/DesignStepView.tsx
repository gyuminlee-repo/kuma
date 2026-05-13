/**
 * DesignStepView — "design" major step sub-step 디스패처.
 *
 * [source: spec §4.1 — DesignStepView (D2.1)]
 * [source: spec Phase E — E2 WizardContainer, E3 SequenceViewer hoist]
 *
 * Sub-step 매핑:
 *   design.load     → SequenceInput (파일 로드)
 *   design.variant  → UniprotSearch + DiversityOptions
 *   design.mutation → MutationInput
 *   design.params   → ParameterPanel + RunDesignAction
 *
 * SequenceViewer는 AppLayout main slot 상단으로 호이스팅 (E3).
 */

import { useAppStore } from "@/store/appStore";
import { SequenceInput } from "@/components/panels/InputPanel/SequenceInput";
import { UniprotSearch } from "@/components/panels/InputPanel/UniprotSearch";
import { DiversityOptions } from "@/components/panels/InputPanel/DiversityOptions";
import { MutationInput } from "@/components/panels/InputPanel/MutationInput";
import { ParameterPanel } from "@/components/panels/ParameterPanel";
import { RunDesignAction } from "./RunDesignAction";
import { WizardContainer } from "./WizardContainer";

const TOTAL_STEPS = 4;

export function DesignStepView() {
  const subStep = useAppStore((s) => s.currentSubStep);
  const goToNextStep = useAppStore((s) => s.goToNextStep);
  const goToPrevStep = useAppStore((s) => s.goToPrevStep);

  switch (subStep) {
    case "design.load":
      return (
        <WizardContainer
          stepIndex={1}
          stepTotal={TOTAL_STEPS}
          titleKey="phaseC.subSteps.design.load"
          descriptionKey="phaseE.descriptions.design.load"
          onNext={() => goToNextStep()}
          onPrev={undefined}
        >
          <SequenceInput />
        </WizardContainer>
      );
    case "design.variant":
      return (
        <WizardContainer
          stepIndex={2}
          stepTotal={TOTAL_STEPS}
          titleKey="phaseC.subSteps.design.variant"
          descriptionKey="phaseE.descriptions.design.variant"
          onNext={() => goToNextStep()}
          onPrev={() => goToPrevStep()}
        >
          <UniprotSearch />
          <DiversityOptions />
        </WizardContainer>
      );
    case "design.mutation":
      return (
        <WizardContainer
          stepIndex={3}
          stepTotal={TOTAL_STEPS}
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
          stepIndex={4}
          stepTotal={TOTAL_STEPS}
          titleKey="phaseC.subSteps.design.params"
          descriptionKey="phaseE.descriptions.design.params"
          onPrev={() => goToPrevStep()}
        >
          <ParameterPanel />
          <RunDesignAction />
        </WizardContainer>
      );
    default:
      return null;
  }
}
