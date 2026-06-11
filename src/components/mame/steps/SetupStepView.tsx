/**
 * SetupStepView — "setup" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 * [updated: 3→2 step — setup.output merged into setup.design]
 * [updated: 2→1 step — setup.files + setup.design merged into a single
 *   "Barcode Package" step. setup.design retained as a legacy/redirect id.]
 *
 * Sub-step 매핑:
 *   setup.files  → BarcodeSetupPanel (embedded, 전체 섹션) — 입력 파일 + 유전자 좌표
 *                  + 프로젝트 메타 + (고급) 플랭크/바인딩 + 출력 위치 + Generate Package
 *
 * WizardContainer: setup phase는 단일 sub-step. Generate가 완료돼야 Next 허용.
 */

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { BarcodeSetupPanel } from "@/components/mame/panels/BarcodeSetupPanel";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { StepRedirectFallback } from "./StepRedirectFallback";

const SETUP_TOTAL = 1;
const SETUP_CONFIG = {
  index: 1,
  label: "1.1",
  progressLabel: `1.1 / ${SETUP_TOTAL}`,
  titleKey: "phaseC.mameSubSteps.setup.files",
  descriptionKey: "phaseE.mameDescriptions.setup.files",
} as const;

export function SetupStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);

  // setup.design is a legacy id (merged into setup.files); render the same
  // merged panel for it. Any non-setup sub-step redirects to setup.files.
  if (subStep !== "setup.files" && subStep !== "setup.design") {
    return (
      <StepRedirectFallback
        currentSub={subStep}
        expectedFor="setup"
        setSubStep={setMameSubStep}
      />
    );
  }

  return (
    <WizardContainer
      stepIndex={SETUP_CONFIG.index}
      stepTotal={SETUP_TOTAL}
      stepLabel={SETUP_CONFIG.label}
      progressLabel={SETUP_CONFIG.progressLabel}
      titleKey={SETUP_CONFIG.titleKey}
      descriptionKey={SETUP_CONFIG.descriptionKey}
      onPrev={undefined}
      onNext={goToNextStep}
      validateBeforeNext={() =>
        useMameAppStore.getState().rawRunParams.customBarcodesPath
          ? { ok: true }
          : {
              ok: false,
              missing: ["mame.barcodeSetup.requireBarcodePackage"],
            }
      }
    >
      <BarcodeSetupPanel embedded />
    </WizardContainer>
  );
}
