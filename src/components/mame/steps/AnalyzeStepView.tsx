/**
 * AnalyzeStepView — "analyze" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec §D3.2 — Run/Cancel/Validate/Clear/Export footer 흡수]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 *
 * Sub-step 매핑:
 *   analyze.inputs  → InputPanel + ParameterPanel + Run/Validate/Cancel action row
 *   analyze.verdict → SummaryRow + VerdictTable
 *   analyze.plate   → PlateView
 *   analyze.health  → RunHealthPanel
 *
 * WizardContainer 전략:
 *   - analyze.inputs: Next = "Run Analysis" (isAnalyzing 중 = "Cancel").
 *     Validate / Clear / Export는 children 내부 secondary row로 표시.
 *   - analyze.verdict/plate/health: Next = 일반 다음 sub-step 이동.
 *   - Ctrl/Cmd+Enter는 MameAppLayout 레벨에서 독립적으로 처리됨.
 */

import { AlertCircle, Download, ShieldCheck, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { selectCanRun } from "@/store/mame/selectors";
import { DataPanel } from "@/components/ui/Panel";
import { SummaryRow } from "@/components/mame/widgets/SummaryRow";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { RunHealthPanel } from "@/components/mame/widgets/RunHealthPanel";
import { InputPanel } from "@/components/mame/panels/InputPanel";
import { ParameterPanel } from "@/components/mame/panels/ParameterPanel";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { WizardContainer } from "@/components/steps/WizardContainer";
import type { RunHealthData } from "@/types/mame/models";

interface AnalyzeStepViewProps {
  /** RunHealthPanel에 전달할 health 데이터. null이면 health sub-step에서 패널 숨김. */
  runHealth?: RunHealthData | null;
  /** Pre-flight-wrapped Run trigger from MameAppLayout. */
  onRunRequest?: () => void;
  /** Clear results request (MameAppLayout이 confirm dialog 담당). */
  onClearRequest?: () => void;
}

const STEP_CONFIG = {
  "analyze.inputs": {
    index: 1,
    titleKey: "phaseC.mameSubSteps.analyze.inputs",
    descriptionKey: "phaseE.mameDescriptions.analyze.inputs",
  },
  "analyze.verdict": {
    index: 2,
    titleKey: "phaseC.mameSubSteps.analyze.verdict",
    descriptionKey: "phaseE.mameDescriptions.analyze.verdict",
  },
  "analyze.plate": {
    index: 3,
    titleKey: "phaseC.mameSubSteps.analyze.plate",
    descriptionKey: "phaseE.mameDescriptions.analyze.plate",
  },
  "analyze.health": {
    index: 4,
    titleKey: "phaseC.mameSubSteps.analyze.health",
    descriptionKey: "phaseE.mameDescriptions.analyze.health",
  },
} as const;

export function AnalyzeStepView({ runHealth = null, onRunRequest, onClearRequest }: AnalyzeStepViewProps = {}) {
  const { t } = useTranslation();
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const isValidating = useMameAppStore((s) => s.isValidating);
  const analyzeProgress = useMameAppStore((s) => s.analyzeProgress);
  const analyzeMessage = useMameAppStore((s) => s.analyzeMessage);
  const validationErrors = useMameAppStore((s) => s.validationErrors);
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  const cancelAnalysis = useMameAppStore((s) => s.cancelAnalysis);
  const validateInputs = useMameAppStore((s) => s.validateInputs);
  const openExport = useMameAppStore((s) => s.openExport);
  const runAnalysis = useMameAppStore((s) => s.runAnalysis);
  const canRun = useMameAppStore(selectCanRun);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);

  if (
    subStep !== "analyze.inputs" &&
    subStep !== "analyze.verdict" &&
    subStep !== "analyze.plate" &&
    subStep !== "analyze.health"
  ) {
    return null;
  }

  const config = STEP_CONFIG[subStep];

  // analyze.inputs: Next = Run/Cancel 버튼 (wizard footer에 배치)
  // 나머지: Next = 일반 이동
  let wizardOnNext: (() => void) | undefined;

  if (subStep === "analyze.inputs") {
    if (isAnalyzing) {
      wizardOnNext = () => void cancelAnalysis();
    } else {
      wizardOnNext = canRun ? () => (onRunRequest ? onRunRequest() : void runAnalysis()) : undefined;
    }
  } else {
    // 마지막 sub-step에서도 Next를 허용 (다음 phase로 이동)
    wizardOnNext = goToNextStep;
  }

  // 메인 콘텐츠 영역
  let mainContent: React.ReactNode;
  switch (subStep) {
    case "analyze.inputs":
      mainContent = (
        <div className="flex flex-col gap-3">
          {/* Progress 및 상태 */}
          <div className="space-y-1 px-1">
            <div className="truncate text-body font-medium text-foreground" aria-live="polite">
              {analyzeMessage || (isAnalyzing ? t("mameSidebar.statusAnalyzing") : canRun ? t("mameSidebar.statusReady") : t("mameSidebar.statusIncomplete"))}
            </div>
            {isAnalyzing && (
              <Progress
                value={analyzeProgress}
                className="mt-1.5 h-1"
                aria-label={t("mameSidebar.analysisProgressAria", { percent: analyzeProgress })}
              />
            )}
            {!isAnalyzing && validationErrors.length > 0 && (
              <p className="mt-1.5 text-caption text-muted-foreground">
                {t("mameSidebar.validationIssues", { count: validationErrors.length })}
              </p>
            )}
          </div>

          {validationErrors.length > 0 && (
            <div
              className="flex items-start gap-2 rounded-control border border-error/40 bg-error/8 px-2.5 py-1.5"
              role="alert"
            >
              <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-error" aria-hidden="true" />
              <div className="min-w-0 space-y-1 text-caption text-error">
                <p className="font-medium">{t("mameSidebar.inputErrors", { count: validationErrors.length })}</p>
                <ul className="list-disc space-y-0.5 pl-4">
                  {validationErrors.map((error, index) => (
                    <li key={`${index}-${error}`} className="break-words">
                      {error}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Secondary action row: Validate / Clear / Export */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-control flex-1 min-w-0 gap-1.5 rounded-control text-caption"
              onClick={() => void validateInputs()}
              disabled={isValidating || isAnalyzing}
            >
              <ShieldCheck size={12} aria-hidden="true" />
              {isValidating ? t("mameSidebar.validatingBtn") : t("mameSidebar.validateBtn")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-control flex-1 min-w-0 gap-1.5 rounded-control text-caption"
              onClick={onClearRequest}
              disabled={!hasResults || isAnalyzing}
            >
              <Trash2 size={12} aria-hidden="true" />
              {t("mameSidebar.clearBtn")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-control flex-1 min-w-0 gap-1.5 rounded-control text-caption"
              onClick={openExport}
              disabled={!hasResults}
            >
              <Download size={12} aria-hidden="true" />
              {t("mameSidebar.exportBtn")}
            </Button>
          </div>

          <InputPanel />
          <ParameterPanel />
        </div>
      );
      break;
    case "analyze.verdict":
      mainContent = (
        <div className="flex flex-col gap-3 h-full overflow-hidden">
          <SummaryRow />
          <DataPanel title={t("mame.appLayout.verdictTableTitle")} className="flex-1 min-h-0">
            <VerdictTable />
          </DataPanel>
        </div>
      );
      break;
    case "analyze.plate":
      mainContent = (
        <div className="flex flex-col gap-3 h-full overflow-hidden">
          <DataPanel title={t("mame.appLayout.platePlanTitle")} className="flex-1 min-h-0">
            <PlateView />
          </DataPanel>
        </div>
      );
      break;
    case "analyze.health":
      mainContent = (
        <div className="flex flex-col gap-3 h-full overflow-hidden">
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
      break;
    default:
      mainContent = null;
  }

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={4}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      onPrev={goToPrevStep}
      onNext={wizardOnNext}
      nextLabelKey={
        subStep === "analyze.inputs"
          ? isAnalyzing
            ? "mameSidebar.cancelBtn"
            : "mameSidebar.runBtn"
          : undefined
      }
    >
      {mainContent}
    </WizardContainer>
  );
}
