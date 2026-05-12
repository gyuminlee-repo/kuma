/**
 * ExportStepView — sub-step dispatcher for "export" major step.
 *
 * [source: spec §1 — Export major, 1 sub-step (D1.1)]
 *
 * Sub-step mapping:
 *   export.all → ExportFormatSelector + OrderSummary + WorkspaceSaveLoad (D2.3에서 layout 정리)
 */

import type { SubStepId } from "@/store/slices/navigationSlice";
import { ExportFormatSelector } from "./ExportFormatSelector";
import { OrderSummary } from "./OrderSummary";
import { WorkspaceSaveLoad } from "./WorkspaceSaveLoad";

interface ExportStepViewProps {
  subStep: SubStepId;
}

export function ExportStepView({ subStep: _subStep }: ExportStepViewProps) {
  // export.all is now the only sub-step; render all export sections (D2.3에서 layout 정리)
  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <ExportFormatSelector />
      <OrderSummary />
      <WorkspaceSaveLoad />
    </div>
  );
}
