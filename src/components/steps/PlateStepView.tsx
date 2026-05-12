/**
 * PlateStepView — "plate" major step 단일 페이지.
 *
 * [source: spec §1 — Plate Mapping major, 1 sub-step (D2.2)]
 *
 * PlateMap은 내부에서 store를 직접 구독하므로 props 없이 마운트.
 */

import { PlateMap } from "@/components/widgets/PlateMap";

export function PlateStepView() {
  return (
    <div className="p-6">
      <PlateMap />
    </div>
  );
}
