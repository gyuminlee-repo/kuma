/**
 * MajorStepView — major-level dispatcher.
 *
 * [source: spec §4.1 — MajorStepView dispatcher (D2.1)]
 * [source: spec Phase G — 3-tab (Design / Output / Export)]
 *
 * Routes currentMajor → appropriate *StepView component.
 */

import { useAppStore } from "@/store/appStore";
import { DesignStepView } from "./DesignStepView";
import { OutputStepView } from "./OutputStepView";
import { ExportStepView } from "./ExportStepView";

export function MajorStepView() {
  const major = useAppStore((s) => s.currentMajor);

  switch (major) {
    case "design":
      return <DesignStepView />;
    case "output":
      return <OutputStepView />;
    case "export":
      return <ExportStepView />;
  }
}
