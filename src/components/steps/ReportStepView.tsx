/**
 * ReportStepView — "report" major step 단일 페이지.
 *
 * [source: spec Phase F — F1 Report 탭 신설]
 *
 * ResultTable + design 통계 (primer 수, plate 추정, rescue stats)
 * WizardContainer로 감쌈. onPrev=Design, onNext=Plate Map
 * stepIndex=1, stepTotal=1 (각 major별 sub-step 카운팅 v1 단순화)
 */

import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "@/store/appStore";
import { ResultTable } from "@/components/widgets/ResultTable";
import { WizardContainer } from "./WizardContainer";
import { StateView } from "@/components/ui/StateView";

export function ReportStepView() {
  const { t } = useTranslation();
  const goToNextStep = useAppStore((s) => s.goToNextStep);
  const goToPrevStep = useAppStore((s) => s.goToPrevStep);

  const { designResults, plateMappings, failedMutations, rescueStats } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
      failedMutations: s.failedMutations,
      rescueStats: s.rescueStats,
    })),
  );

  const primerCount = designResults.length;
  const plateCount = Math.ceil(plateMappings.filter((m) => m.primer_type === "forward").length / 96) || 0;
  const failedCount = failedMutations.length;
  const rescueCount = (rescueStats?.pool_cascade ?? 0) + (rescueStats?.auto_relax ?? 0);

  const hasResults = designResults.length > 0;

  return (
    <WizardContainer
      stepIndex={1}
      stepTotal={1}
      titleKey="phaseC.subSteps.report.summary"
      descriptionKey="phaseE.descriptions.report.summary"
      onPrev={() => goToPrevStep()}
      onNext={() => goToNextStep()}
    >
      {!hasResults ? (
        <div className="flex h-48 items-center justify-center">
          <StateView
            variant="empty"
            title={t("report.noResultsTitle")}
            description={t("report.noResultsDesc")}
          />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Design statistics summary */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label={t("report.stats.primers")} value={primerCount} colorClass="text-success" />
            <StatCard label={t("report.stats.plates")} value={plateCount} colorClass="text-info" />
            <StatCard label={t("report.stats.failed")} value={failedCount} colorClass={failedCount > 0 ? "text-error" : "text-muted-foreground"} />
            <StatCard label={t("report.stats.rescued")} value={rescueCount} colorClass={rescueCount > 0 ? "text-warning" : "text-muted-foreground"} />
          </div>

          {/* Result table */}
          <ResultTable />
        </div>
      )}
    </WizardContainer>
  );
}

function StatCard({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: number;
  colorClass: string;
}) {
  return (
    <div className="rounded-container border border-border bg-card p-3 text-center">
      <div className={`text-2xl font-bold tabular-nums ${colorClass}`}>{value}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
