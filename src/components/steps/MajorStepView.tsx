/**
 * MajorStepView — major-level dispatcher.
 *
 * [source: spec §4.1 — MajorStepView dispatcher]
 *
 * Routes currentMajor → appropriate *StepView component.
 * Each *StepView receives the currentSubStep and handles sub-step routing internally.
 */

import { useAppStore } from "@/store/appStore";
import { VariantStepView } from "./VariantStepView";
import { SdmStepView } from "./SdmStepView";
import { PlateStepView } from "./PlateStepView";
import { ExportStepView } from "./ExportStepView";

export function MajorStepView() {
  const major = useAppStore((s) => s.currentMajor);
  const subStep = useAppStore((s) => s.currentSubStep);

  switch (major) {
    case "variant":
      return <VariantStepView subStep={subStep} />;
    case "sdm":
      return <SdmStepView subStep={subStep} />;
    case "plate":
      return <PlateStepView subStep={subStep} />;
    case "export":
      return <ExportStepView subStep={subStep} />;
  }
}
