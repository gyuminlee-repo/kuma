/**
 * AnalyzeStepView — "analyze" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 *
 * Sub-step 매핑:
 *   analyze.verdict → SummaryRow + VerdictTable
 *   analyze.plate   → PlateView
 *   analyze.health  → RunHealthPanel
 *
 * NOTE: D3.2 전까지 이 컴포넌트는 mount되지 않는다.
 * MameAppLayout 슬롯 교체는 D3.2에서 수행한다.
 */

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { DataPanel } from "@/components/ui/Panel";
import { SummaryRow } from "@/components/mame/widgets/SummaryRow";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { RunHealthPanel } from "@/components/mame/widgets/RunHealthPanel";
import { useTranslation } from "react-i18next";
import type { RunHealthData } from "@/types/mame/models";

interface AnalyzeStepViewProps {
  /** RunHealthPanel에 전달할 health 데이터. null이면 health sub-step에서 패널 숨김. */
  runHealth?: RunHealthData | null;
}

export function AnalyzeStepView({ runHealth = null }: AnalyzeStepViewProps = {}) {
  const { t } = useTranslation();
  const subStep = useMameAppStore((s) => s.currentMameSubStep);

  switch (subStep) {
    case "analyze.verdict":
      return (
        <div className="flex flex-col gap-3 p-3 h-full overflow-hidden">
          <SummaryRow />
          <DataPanel title={t("mame.appLayout.verdictTableTitle")} className="flex-1 min-h-0">
            <VerdictTable />
          </DataPanel>
        </div>
      );
    case "analyze.plate":
      return (
        <div className="flex flex-col gap-3 p-3 h-full overflow-hidden">
          <DataPanel title={t("mame.appLayout.platePlanTitle")} className="flex-1 min-h-0">
            <PlateView />
          </DataPanel>
        </div>
      );
    case "analyze.health":
      return (
        <div className="flex flex-col gap-3 p-3 h-full overflow-hidden">
          {runHealth !== null ? (
            <DataPanel title={t("mame.appLayout.runHealthTitle")} className="flex-1 min-h-0">
              <RunHealthPanel health={runHealth} />
            </DataPanel>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
              {t("mame.analyze.healthNoData", "Run analysis to see health metrics.")}
            </div>
          )}
        </div>
      );
    default:
      return null;
  }
}
