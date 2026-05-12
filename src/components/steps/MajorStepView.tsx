/**
 * MajorStepView — major-level dispatcher.
 *
 * [source: spec §4.1 — MajorStepView dispatcher]
 *
 * Routes currentMajor → appropriate *StepView component.
 * design case: placeholder until D2.1 (DesignStepView).
 */

import { useAppStore } from "@/store/appStore";
import { PlateStepView } from "./PlateStepView";
import { ExportStepView } from "./ExportStepView";

export function MajorStepView() {
  const major = useAppStore((s) => s.currentMajor);
  const subStep = useAppStore((s) => s.currentSubStep);

  switch (major) {
    case "design":
      // D2.1에서 DesignStepView로 교체 예정
      return (
        <div
          className="flex flex-1 items-center justify-center text-muted-foreground"
          data-testid="design-placeholder"
        >
          Design
        </div>
      );
    case "plate":
      return <PlateStepView subStep={subStep} />;
    case "export":
      return <ExportStepView subStep={subStep} />;
  }
}
