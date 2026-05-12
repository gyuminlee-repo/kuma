/**
 * DesignStepView — "design" major step sub-step 디스패처.
 *
 * [source: spec §4.1 — DesignStepView (D2.1)]
 *
 * Sub-step 매핑:
 *   design.load     → SequenceInput (파일 로드)
 *   design.variant  → UniprotSearch + DiversityOptions
 *   design.mutation → MutationInput
 *   design.params   → ParameterPanel + RunDesignAction
 */

import { useAppStore } from "@/store/appStore";
import { SequenceViewer } from "@/components/widgets/SequenceViewer";
import { SequenceInput } from "@/components/panels/InputPanel/SequenceInput";
import { UniprotSearch } from "@/components/panels/InputPanel/UniprotSearch";
import { DiversityOptions } from "@/components/panels/InputPanel/DiversityOptions";
import { MutationInput } from "@/components/panels/InputPanel/MutationInput";
import { ParameterPanel } from "@/components/panels/ParameterPanel";
import { RunDesignAction } from "./RunDesignAction";

export function DesignStepView() {
  const subStep = useAppStore((s) => s.currentSubStep);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0 border-b border-border">
        <SequenceViewer />
      </div>
      <div className="flex-1 overflow-auto p-6">
        {(() => {
          switch (subStep) {
            case "design.load":
              return <SequenceInput />;
            case "design.variant":
              return (
                <>
                  <UniprotSearch />
                  <DiversityOptions />
                </>
              );
            case "design.mutation":
              return <MutationInput />;
            case "design.params":
              return (
                <>
                  <ParameterPanel />
                  <RunDesignAction />
                </>
              );
            default:
              return null;
          }
        })()}
      </div>
    </div>
  );
}
