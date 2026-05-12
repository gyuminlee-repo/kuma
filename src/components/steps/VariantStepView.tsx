/**
 * VariantStepView — sub-step dispatcher for "variant" major step.
 *
 * [source: spec §1 — Variant Selection major, 5 sub-steps]
 *
 * Sub-step mapping:
 *   variant.load     → SequenceInput (file load 부분)
 *   variant.select   → UniprotSearch
 *   variant.adaptive → DiversityOptions (adaptive 옵션)
 *   variant.domain   → DiversitySections (전체 마운트 — Stage 3에서 domain 분할)
 *   variant.pareto   → DiversitySections (전체 마운트 — Stage 3에서 pareto 분할)
 *
 * NOTE: variant.domain과 variant.pareto 모두 DiversitySections 전체를 렌더링.
 * 두 sub-step 간 동일 UI가 표시되는 것은 Stage 2 의도된 동작 (Stage 3에서 분할).
 */


import { SequenceInput } from "@/components/panels/InputPanel/SequenceInput";
import { UniprotSearch } from "@/components/panels/InputPanel/UniprotSearch";
import { DiversityOptions } from "@/components/panels/InputPanel/DiversityOptions";
import { SequenceViewer } from "@/components/widgets/SequenceViewer";
// DiversitySections exports sub-section components (DomainAllocationSection etc.) but
// no single top-level export. DiversityOptions composes them internally.
// variant.domain / variant.pareto mount DiversityOptions (full) in Stage 2.
// TODO Stage 3: split DiversitySections into domain-only / pareto-only mounts.

interface VariantStepViewProps {
  subStep: string; // D2.1: will be replaced by DesignStepView
}

export function VariantStepView({ subStep }: VariantStepViewProps) {
  switch (subStep) {
    case "variant.load":
      return (
        <div className="flex flex-col w-full h-full overflow-hidden">
          <div className="overflow-y-auto p-4 shrink-0">
            <SequenceInput />
          </div>
          <div className="flex-1 overflow-hidden">
            <SequenceViewer />
          </div>
        </div>
      );
    case "variant.select":
      return (
        <div className="w-full h-full overflow-y-auto p-4">
          <UniprotSearch />
        </div>
      );
    case "variant.adaptive":
      return (
        <div className="w-full h-full overflow-y-auto p-4">
          <DiversityOptions />
        </div>
      );
    case "variant.domain":
      // TODO Stage 3: mount only domain section (DomainAllocationSection) of DiversityOptions.
      // Currently full DiversityOptions mounted — Stage 3 splits by section prop.
      return (
        <div className="w-full h-full overflow-y-auto p-4">
          <DiversityOptions />
        </div>
      );
    case "variant.pareto":
      // TODO Stage 3: mount only pareto/Cα section (OptimizationSummarySection) of DiversityOptions.
      return (
        <div className="w-full h-full overflow-y-auto p-4">
          <DiversityOptions />
        </div>
      );
    default:
      return null;
  }
}
