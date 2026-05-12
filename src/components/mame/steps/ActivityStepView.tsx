/**
 * ActivityStepView — "activity" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 *
 * Sub-step 매핑:
 *   activity.ingest → IngestSection (CSV/Excel 업로드 + WT 어노테이션)
 *   activity.merge  → MergeSection (genotype merge + replicate priority)
 *   activity.export → ExportSection (EVOLVEpro xlsx 저장 + round handoff)
 *
 * ActivityPanel은 wrapper로 유지되므로 테스트 호환성 유지.
 * NOTE: D3.2 전까지 이 컴포넌트는 mount되지 않는다.
 */

import { useEffect } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { IngestSection, MergeSection, ExportSection } from "@/components/mame/panels/ActivityPanel";

export function ActivityStepView() {
  const subStep = useMameAppStore((s) => s.currentMameSubStep);

  // Auto-create a round if none exists (mirrors ActivityPanel behavior)
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const addRound = useRoundStore((s) => s.addRound);
  useEffect(() => {
    if (activeRoundId === null) {
      addRound({ plate_meta: { plates: [] } });
    }
  }, [activeRoundId, addRound]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="content-card space-y-6">
        {(() => {
          switch (subStep) {
            case "activity.ingest":
              return <IngestSection />;
            case "activity.merge":
              return <MergeSection />;
            case "activity.export":
              return <ExportSection />;
            default:
              return null;
          }
        })()}
      </div>
    </div>
  );
}
