/**
 * AnalyzeStepView — "analyze" mame phase sub-step 디스패처.
 *
 * [source: spec §D2.4 — mame StepView 신규]
 * [updated: spec §D3.2 — Run/Cancel/Validate/Clear/Export footer 흡수]
 * [updated: spec Phase F F6 — WizardContainer 적용]
 * [updated: spec Phase G #18 — analyze.health 폐지, RunHealth 섹션을 verdict/plate에 흡수]
 *
 * Sub-step 매핑 (patch-260514 Task #12 — analyze.verdict + analyze.plate 통합):
 *   analyze.inputs  → InputPanel + ParameterPanel + Run/Validate/Cancel action row
 *   analyze.review  → 좌: SummaryRow + VerdictTable / 우상: PlateView / 우하: per-plate verdict chart
 *
 * Legacy analyze.verdict / analyze.plate ids 진입 시 StepRedirectFallback 으로 분기 → analyze.inputs.
 *
 * WizardContainer 전략:
 *   - analyze.inputs: Next = "Run Analysis" (isAnalyzing 중 = "Cancel").
 *     Validate / Clear / Export는 children 내부 secondary row로 표시.
 *   - analyze.review: Next = 일반 다음 sub-step 이동.
 *   - Ctrl/Cmd+Enter는 MameAppLayout 레벨에서 독립적으로 처리됨.
 */

import { AlertCircle, Download, ShieldCheck, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { selectCanRun } from "@/store/mame/selectors";
import { DataPanel } from "@/components/ui/Panel";
import { SummaryRow } from "@/components/mame/widgets/SummaryRow";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { RunHealthPanel } from "@/components/mame/widgets/RunHealthPanel";
import { PlateClusterAlert } from "@/components/mame/widgets/PlateClusterAlert";
import { InputPanel } from "@/components/mame/panels/InputPanel";
import { ParameterPanel } from "@/components/mame/panels/ParameterPanel";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { StepRedirectFallback } from "./StepRedirectFallback";
import type { RunHealthData } from "@/types/mame/models";

interface AnalyzeStepViewProps {
  /** RunHealthPanel에 전달할 health 데이터. null이면 health sub-step에서 패널 숨김. */
  runHealth?: RunHealthData | null;
  /** Pre-flight-wrapped Run trigger from MameAppLayout. */
  onRunRequest?: () => void;
  /** Clear results request (MameAppLayout이 confirm dialog 담당). */
  onClearRequest?: () => void;
}

const ANALYZE_TOTAL = 2;
const STEP_CONFIG = {
  "analyze.inputs": {
    index: 1,
    label: "2.1",
    progressLabel: `2.1 / ${ANALYZE_TOTAL}`,
    titleKey: "phaseC.mameSubSteps.analyze.inputs",
    descriptionKey: "phaseE.mameDescriptions.analyze.inputs",
  },
  "analyze.review": {
    index: 2,
    label: "2.2",
    progressLabel: `2.2 / ${ANALYZE_TOTAL}`,
    titleKey: "phaseC.mameSubSteps.analyze.review",
    descriptionKey: "phaseE.mameDescriptions.analyze.review",
  },
} as const;

export function AnalyzeStepView({ runHealth = null, onRunRequest, onClearRequest }: AnalyzeStepViewProps = {}) {
  const { t } = useTranslation();
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const isValidating = useMameAppStore((s) => s.isValidating);
  const analyzeProgress = useMameAppStore((s) => s.analyzeProgress);
  const analyzeMessage = useMameAppStore((s) => s.analyzeMessage);
  const analyzeCurrent = useMameAppStore((s) => s.analyzeCurrent);
  const analyzeTotal = useMameAppStore((s) => s.analyzeTotal);
  const validationErrors = useMameAppStore((s) => s.validationErrors);
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  const cancelAnalysis = useMameAppStore((s) => s.cancelAnalysis);
  const validateInputs = useMameAppStore((s) => s.validateInputs);
  const openExport = useMameAppStore((s) => s.openExport);
  const runAnalysis = useMameAppStore((s) => s.runAnalysis);
  const canRun = useMameAppStore(selectCanRun);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);

  // Legacy ids fall through StepRedirectFallback → analyze.inputs.
  if (
    subStep !== "analyze.inputs" &&
    subStep !== "analyze.review"
  ) {
    return (
      <StepRedirectFallback
        currentSub={subStep}
        expectedFor="analyze"
        setSubStep={setMameSubStep}
      />
    );
  }

  const config = STEP_CONFIG[subStep];

  // analyze.inputs: Next = Run/Cancel 버튼 (wizard footer에 배치)
  // 나머지: Next = 일반 이동
  //
  // Next 버튼은 항상 렌더되어야 한다. 미완료 상태에서는 disabled(isValid=false)로 표시하며,
  // onNext 자체를 undefined로 두면 WizardContainer가 버튼을 숨겨 사용자 혼란을 유발한다.
  let wizardOnNext: (() => void) | undefined;
  let wizardIsValid: (() => boolean) | undefined;

  if (subStep === "analyze.inputs") {
    if (isAnalyzing) {
      // 진행 중에는 Cancel로 작동 — 항상 활성
      wizardOnNext = () => void cancelAnalysis();
      wizardIsValid = () => true;
    } else {
      // canRun=false일 때도 버튼은 표시하되 disabled
      wizardOnNext = () => (onRunRequest ? onRunRequest() : void runAnalysis());
      wizardIsValid = () => canRun;
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
            {isAnalyzing && analyzeCurrent !== null && analyzeTotal !== null && (
              <p className="mt-1 text-caption text-muted-foreground" aria-live="polite">
                {analyzeCurrent.toLocaleString()} / {analyzeTotal.toLocaleString()}
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
    case "analyze.review":
      // Unified review: left = Summary + Verdict table, right = Plate (top) + per-plate verdict chart (bottom).
      // Other RunHealth sections (file-size/throughput/pore-yield/barcode/cross-talk) are still reachable from
      // analyze.inputs's RunHealthPanel and the QC inspector; not duplicated here per PI spec slide 6.
      mainContent = (
        <div className="flex h-full min-h-[720px] flex-col">
          <PlateClusterAlert />
          <div className="flex-1 min-h-0">
          <PanelGroup direction="horizontal" autoSaveId="mame.analyze.review.split">
            <Panel defaultSize={50} minSize={25}>
              <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
                <div className="flex-shrink-0">
                  <SummaryRow />
                </div>
                <DataPanel title={t("mame.appLayout.verdictTableTitle")} className="flex-1 min-h-0">
                  <VerdictTable />
                </DataPanel>
              </div>
            </Panel>
            <PanelResizeHandle
              className="w-2 bg-border hover:bg-border/70 transition-colors"
              aria-label={t("mame.appLayout.verdictTableTitle")}
            />
            <Panel defaultSize={50} minSize={25}>
              <PanelGroup direction="vertical" autoSaveId="mame.analyze.review.vsplit">
                <Panel defaultSize={55} minSize={20}>
                  <DataPanel title={t("mame.appLayout.platePlanTitle")} className="h-full min-h-0 overflow-auto">
                    <PlateView />
                  </DataPanel>
                </Panel>
                <PanelResizeHandle
                  className="h-2 bg-border hover:bg-border/70 transition-colors"
                />
                <Panel defaultSize={45} minSize={20}>
                  <DataPanel title={t("mame.appLayout.efficiencyChartTitle")} className="h-full min-h-0 overflow-auto">
                    {runHealth !== null ? (
                      <RunHealthPanel
                        health={runHealth}
                        sections={["verdict-breakdown"]}
                      />
                    ) : (
                      <div className="p-4 text-caption text-muted-foreground">
                        {t("mameSidebar.statusIncomplete")}
                      </div>
                    )}
                  </DataPanel>
                </Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
          </div>
        </div>
      );
      break;
    default:
      mainContent = null;
  }

  return (
    <WizardContainer
      stepIndex={config.index}
      stepTotal={ANALYZE_TOTAL}
      stepLabel={config.label}
      progressLabel={config.progressLabel}
      titleKey={config.titleKey}
      descriptionKey={config.descriptionKey}
      maxWidth={subStep === "analyze.review" ? "full" : "3xl"}
      onPrev={goToPrevStep}
      onNext={wizardOnNext}
      isValid={wizardIsValid}
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
