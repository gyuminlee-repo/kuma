/**
 * PlateStepView — sub-step dispatcher for "plate" major step.
 *
 * [source: spec §1 — Plate Mapping major, 3 sub-steps]
 *
 * Sub-step mapping:
 *   plate.size   → PlateSizeSelector (96/384 toggle)
 *   plate.layout → KuroPlateView (wells wire in Stage 3)
 *   plate.labels → WellLabelOptions (label format selector)
 */

import { useAppStore } from "@/store/appStore";
import type { SubStepId } from "@/store/slices/navigationSlice";
import { KuroPlateView } from "@/components/widgets/KuroPlateView";
import { PlateSizeSelector } from "./PlateSizeSelector";
import { WellLabelOptions } from "./WellLabelOptions";

interface PlateStepViewProps {
  subStep: SubStepId;
}

export function PlateStepView({ subStep }: PlateStepViewProps) {
  const plateMappings = useAppStore((s) => s.plateMappings);

  switch (subStep) {
    case "plate.size":
      return <PlateSizeSelector />;
    case "plate.layout":
      return (
        <div className="w-full h-full overflow-hidden">
          <KuroPlateView plateMappings={plateMappings} />
        </div>
      );
    case "plate.labels":
      return <WellLabelOptions />;
    default:
      return null;
  }
}
