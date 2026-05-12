/**
 * SdmStepView — sub-step dispatcher for "sdm" major step.
 *
 * [source: spec §1 — SDM Design major, 5 sub-steps]
 *
 * Sub-step mapping:
 *   sdm.mutations  → MutationInput
 *   sdm.codon      → ParameterPanelSection (section="codon")
 *   sdm.polymerase → ParameterPanelSection (section="polymerase-tm")
 *   sdm.gc         → ParameterPanelSection (section="gc-length")
 *   sdm.run        → RunDesignAction + ResultTable (run button + results)
 */

import type { SubStepId } from "@/store/slices/navigationSlice";
import { MutationInput } from "@/components/panels/InputPanel/MutationInput";
import { ParameterPanelSection } from "@/components/panels/ParameterPanelSection";
import { ResultTable } from "@/components/widgets/ResultTable";
import { RunDesignAction } from "./RunDesignAction";

interface SdmStepViewProps {
  subStep: SubStepId;
}

export function SdmStepView({ subStep }: SdmStepViewProps) {
  switch (subStep) {
    case "sdm.mutations":
      return (
        <div className="w-full h-full overflow-y-auto p-4">
          <MutationInput />
        </div>
      );
    case "sdm.codon":
      return <ParameterPanelSection section="codon" />;
    case "sdm.polymerase":
      return <ParameterPanelSection section="polymerase-tm" />;
    case "sdm.gc":
      return <ParameterPanelSection section="gc-length" />;
    case "sdm.run":
      return (
        <div className="flex flex-col w-full h-full overflow-hidden">
          <RunDesignAction />
          <div className="flex-1 overflow-hidden">
            <ResultTable />
          </div>
        </div>
      );
    default:
      return null;
  }
}
