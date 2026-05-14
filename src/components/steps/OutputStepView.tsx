/**
 * OutputStepView — "output" major step (Phase G #12).
 *
 * [source: spec Phase G — Report → Output rename + Plate Map 병합 (#12)]
 * [source: spec Phase G — Output 좌우 split: Summary(좌) + PlateMap(우) (#10, #11)]
 * [source: spec Phase G — 통계 4 카드는 단순 텍스트 라인으로 축소 (#10/#11)]
 * [source: spec Phase G — Output maxWidth="full" (#4)]
 *
 * Layout: 좌우 50:50 split — 좌=Summary(ResultTable + 텍스트 통계), 우=PlateMap
 */

import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "@/store/appStore";
import { ResultTable } from "@/components/widgets/ResultTable";
import { PlateMap } from "@/components/widgets/PlateMap";
import { WizardContainer } from "./WizardContainer";
import { StateView } from "@/components/ui/StateView";
import { KURO_STEP_INDEX, TOTAL_KURO_STEPS } from "./constants";

export function OutputStepView() {
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
  const plateCount =
    Math.ceil(plateMappings.filter((m) => m.primer_type === "forward").length / 96) || 0;
  const failedCount = failedMutations.length;
  const rescueCount =
    (rescueStats?.pool_cascade ?? 0) + (rescueStats?.auto_relax ?? 0);

  const hasResults = designResults.length > 0;

  return (
    <WizardContainer
      stepIndex={KURO_STEP_INDEX["output.summary"]}
      stepTotal={TOTAL_KURO_STEPS}
      titleKey="phaseC.subSteps.output.summary"
      descriptionKey="phaseE.descriptions.output.summary"
      maxWidth="full"
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
        <div className="flex h-full min-h-0 gap-4">
          {/* 좌: Summary (ResultTable + 텍스트 통계) */}
          <section
            className="flex w-1/2 min-w-0 flex-col gap-3"
            aria-label={t("phaseC.subSteps.output.summary")}
          >
            {/* 통계 — 4 카드 대신 단순 텍스트 라인 (Phase G #10/#11) */}
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
              <div className="flex gap-1.5">
                <dt>{t("report.stats.primers")}:</dt>
                <dd className="font-semibold tabular-nums text-success">{primerCount}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>{t("report.stats.plates")}:</dt>
                <dd className="font-semibold tabular-nums text-info">{plateCount}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>{t("report.stats.failed")}:</dt>
                <dd
                  className={`font-semibold tabular-nums ${failedCount > 0 ? "text-error" : "text-muted-foreground"}`}
                >
                  {failedCount}
                </dd>
              </div>
              <div className="flex gap-1.5">
                <dt>{t("report.stats.rescued")}:</dt>
                <dd
                  className={`font-semibold tabular-nums ${rescueCount > 0 ? "text-warning" : "text-muted-foreground"}`}
                >
                  {rescueCount}
                </dd>
              </div>
            </dl>

            <div className="flex-1 min-h-0 overflow-auto">
              <ResultTable />
            </div>
          </section>

          {/* 우: PlateMap */}
          <section
            className="flex w-1/2 min-w-0 flex-col"
            aria-label={t("phaseC.subSteps.plate.layout", "Plate Map")}
          >
            <PlateMap />
          </section>
        </div>
      )}
    </WizardContainer>
  );
}
