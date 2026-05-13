/**
 * SetupStepView — "setup" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 *
 * Sub-step 매핑:
 *   setup.files  → BarcodeSetupPanel(group="files")  — 입력 파일 + 유전자 좌표 + 프로젝트 메타
 *   setup.design → BarcodeSetupPanel(group="design") — 플랭크 + 바인딩 파라미터
 *   setup.output → BarcodeSetupPanel(group="output") — 생성 버튼 + 출력 파일
 *
 * WizardContainer: 3 sub-step 순서대로 Next/Prev 탐색.
 * setup.output의 Next는 BarcodeSetupPanel 내부 "Generate Package" 버튼이 담당.
 * wizard footer Next는 setup.output에서 다음 phase(analyze)로 이동하는 데만 사용.
 */

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { BarcodeSetupPanel } from "@/components/mame/panels/BarcodeSetupPanel";
import { WizardContainer } from "@/components/steps/WizardContainer";

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
  "setup.output": {
    index: 3,
    titleKey: "phaseC.mameSubSteps.setup.output",
    descriptionKey: "phaseE.mameDescriptions.setup.output",
  },
} as const;

export function SetupStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);

  if (
    subStep !== "setup.files" &&
    subStep !== "setup.design" &&
    subStep !== "setup.output"
  ) {
    return null;
  }

  const config = STEP_CONFIG[subStep];
  const isFirst = subStep === "setup.files";

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={3}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      onPrev={isFirst ? undefined : goToPrevStep}
      onNext={goToNextStep}
    >
      {subStep === "setup.files" && <BarcodeSetupPanel group="files" />}
      {subStep === "setup.design" && <BarcodeSetupPanel group="design" />}
      {subStep === "setup.output" && <BarcodeSetupPanel group="output" />}
    </WizardContainer>
  );
}
