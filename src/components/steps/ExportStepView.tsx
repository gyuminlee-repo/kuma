/**
 * ExportStepView — "export" major step 단일 페이지.
 *
 * [source: spec §1 — Export major, 1 sub-step (D2.3)]
 * [source: spec Phase G — #8 KURO workspace 완전 제거]
 * [source: spec Phase E — E2 WizardContainer, Phase G #4 maxWidth]
 *
 * Sub-step switch 제거 (export.all 단일 sub-step). 전체 export UI를 단일 페이지로 통합.
 * WorkspaceSaveLoad는 Phase G #8에서 제거됨.
 * WizardContainer로 감싸 Back/Next UX를 DesignStepView/OutputStepView와 통일.
 * onNext=undefined: export는 마지막 major step — Next 버튼 미표시.
 */

import { useAppStore } from "@/store/appStore";
import { WizardContainer } from "./WizardContainer";
import { ExportFormatSelector } from "./ExportFormatSelector";
import { OrderSummary } from "./OrderSummary";

export function ExportStepView() {
  const goToPrevStep = useAppStore((s) => s.goToPrevStep);

  return (
    <WizardContainer
      stepIndex={1}
      stepTotal={1}
      titleKey="phaseC.subSteps.export.all"
      descriptionKey="phaseE.descriptions.export.all"
      maxWidth="4xl"
      onPrev={goToPrevStep}
      onNext={undefined}
    >
      <div className="space-y-6">
        <ExportFormatSelector />
        <OrderSummary />
      </div>
    </WizardContainer>
  );
}
