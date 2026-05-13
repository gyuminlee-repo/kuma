/**
 * MajorStepView — major-level dispatcher.
 *
 * [source: spec §4.1 — MajorStepView dispatcher (D2.1)]
 * [source: spec Phase F — F1 Report 탭 신설 (4-major)]
 *
 * Routes currentMajor → appropriate *StepView component.
 */

import { useAppStore } from "@/store/appStore";
import { DesignStepView } from "./DesignStepView";
import { ReportStepView } from "./ReportStepView";
import { PlateStepView } from "./PlateStepView";
import { ExportStepView } from "./ExportStepView";

export function MajorStepView() {
  const major = useAppStore((s) => s.currentMajor);

  switch (major) {
    case "design":
      return <DesignStepView />;
    case "report":
      return <ReportStepView />;
    case "plate":
      return <PlateStepView />;
    case "export":
      return <ExportStepView />;
  }
}
