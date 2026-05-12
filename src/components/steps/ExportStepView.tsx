/**
 * ExportStepView — sub-step dispatcher for "export" major step.
 *
 * [source: spec §1 — Export major, 3 sub-steps]
 *
 * Sub-step mapping:
 *   export.format    → ExportFormatSelector (IDT CSV / Twist CSV / FASTA)
 *   export.summary   → OrderSummary (plate/primer/mutation statistics)
 *   export.workspace → WorkspaceSaveLoad (getWorkspaceSnapshot / loadWorkspace)
 */

import type { SubStepId } from "@/store/slices/navigationSlice";
import { ExportFormatSelector } from "./ExportFormatSelector";
import { OrderSummary } from "./OrderSummary";
import { WorkspaceSaveLoad } from "./WorkspaceSaveLoad";

interface ExportStepViewProps {
  subStep: SubStepId;
}

export function ExportStepView({ subStep }: ExportStepViewProps) {
  switch (subStep) {
    case "export.format":
      return <ExportFormatSelector />;
    case "export.summary":
      return <OrderSummary />;
    case "export.workspace":
      return <WorkspaceSaveLoad />;
    default:
      return null;
  }
}
