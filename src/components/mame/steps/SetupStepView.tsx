/**
 * SetupStepView — "setup" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 * [updated: 3→2 step — setup.output merged into setup.design]
 *
 * Sub-step 매핑:
 *   setup.files  → BarcodeSetupPanel(group="files")  — 입력 파일 + 유전자 좌표 + 프로젝트 메타
 *   setup.design → BarcodeSetupPanel(group="design") — 플랭크 + 바인딩 파라미터 + Generate Package
 *
 * WizardContainer: 2 sub-step 순서대로 Next/Prev 탐색.
 */

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { BarcodeSetupPanel } from "@/components/mame/panels/BarcodeSetupPanel";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { StepRedirectFallback } from "./StepRedirectFallback";

const STEP_CONFIG = {
  "setup.files": {
    index: 1,
    titleKey: "phaseC.mameSubSteps.setup.files",
    descriptionKey: "phaseE.mameDescriptions.setup.files",
  },
  "setup.design": {
    index: 2,
    titleKey: "phaseC.mameSubSteps.setup.design",
    descriptionKey: "phaseE.mameDescriptions.setup.design",
  },
} as const;

export function SetupStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);

  if (subStep !== "setup.files" && subStep !== "setup.design") {
    return (
      <StepRedirectFallback
        currentSub={subStep}
        expectedFor="setup"
        setSubStep={setMameSubStep}
      />
    );
  }

  const config = STEP_CONFIG[subStep];
  const isFirst = subStep === "setup.files";

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={2}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      onPrev={isFirst ? undefined : goToPrevStep}
      onNext={goToNextStep}
    >
      {subStep === "setup.files" && <BarcodeSetupPanel group="files" />}
      {subStep === "setup.design" && <BarcodeSetupPanel group="design" />}
    </WizardContainer>
  );
}
