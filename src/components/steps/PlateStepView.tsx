/**
 * PlateStepView — sub-step dispatcher for "plate" major step.
 *
 * [source: spec §1 — Plate Mapping major, 1 sub-step (D1.1)]
 *
 * Sub-step mapping:
 *   plate.layout → KuroPlateView
 */

import { useAppStore } from "@/store/appStore";
import type { SubStepId } from "@/store/slices/navigationSlice";
import { KuroPlateView } from "@/components/widgets/KuroPlateView";

interface PlateStepViewProps {
  subStep: SubStepId;
}

export function PlateStepView({ subStep: _subStep }: PlateStepViewProps) {
  const plateMappings = useAppStore((s) => s.plateMappings);

  // plate.layout is now the only sub-step; render directly
  return (
    <div className="w-full h-full overflow-hidden">
      <KuroPlateView plateMappings={plateMappings} />
    </div>
  );
}
