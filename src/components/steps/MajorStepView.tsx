/**
 * MajorStepView — major-level dispatcher.
 *
 * [source: spec §4.1 — MajorStepView dispatcher (D2.1)]
 *
 * Routes currentMajor → appropriate *StepView component.
 */

import { useAppStore } from "@/store/appStore";
import { DesignStepView } from "./DesignStepView";
import { PlateStepView } from "./PlateStepView";
import { ExportStepView } from "./ExportStepView";

export function MajorStepView() {
  const major = useAppStore((s) => s.currentMajor);

  switch (major) {
    case "design":
      return <DesignStepView />;
    case "plate":
      return <PlateStepView />;
    case "export":
      return <ExportStepView />;
  }
}
