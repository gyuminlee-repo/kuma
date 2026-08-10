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
 *
 * Janus 는 이 화면에 없다. 설정도, 실행이 장비용 파일을 썼다는 안내도 step 3
 * (JanusStepView) 소관이다. 시퀀싱 판정만 필요한 운용자는 step 2 에서 멈추므로,
 * 그 경로에 장비 이야기가 끼어들 이유가 없다. 안내만 남겨 두었더니 입력을 바꾼 뒤에도
 * 이전 실행이 쓴 파일을 계속 알리는 자리가 되어, 화면이 끝난 실행을 현재로 보이게 했다.
 */

import { AlertCircle, Download, ShieldCheck, Trash2 } from "lucide-react";
import { MissingInputsBanner } from "@/components/mame/panels/MissingInputsBanner";
import { computeEtaFromElapsed } from "@/lib/eta";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { selectCanRun } from "@/store/mame/selectors";
import { DataPanel } from "@/components/ui/Panel";
import { SummaryRow } from "@/components/mame/widgets/SummaryRow";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { RunHealthPanel } from "@/components/mame/widgets/RunHealthPanel";
import { PlateClusterAlert } from "@/components/mame/widgets/PlateClusterAlert";
import { MappingIntegrityAlert } from "@/components/mame/widgets/MappingIntegrityAlert";
import { RunQualityNotice } from "@/components/mame/widgets/RunQualityNotice";
import { ExcludedOccupantsNotice } from "@/components/mame/widgets/ExcludedOccupantsNotice";
import { OffLayoutRecordsNotice } from "@/components/mame/widgets/OffLayoutRecordsNotice";
import { ReferenceResolutionNotice } from "@/components/mame/widgets/ReferenceResolutionNotice";
import { LegacySampleMapNotice } from "@/components/mame/widgets/LegacySampleMapNotice";
import { DemuxResumeNotice } from "@/components/mame/widgets/DemuxResumeNotice";
import { EmptyAnalysisNotice } from "@/components/mame/widgets/EmptyAnalysisNotice";
import { ContaminationPanel } from "@/components/mame/widgets/ContaminationPanel";
import { PlateOrderNotice } from "@/components/mame/widgets/PlateOrderNotice";
import { ReplicateModeNotice } from "@/components/mame/widgets/ReplicateModeNotice";
import { RestoredResultNotice } from "@/components/mame/widgets/RestoredResultNotice";
import { AnalyzeDurationDialog } from "@/components/mame/dialogs/AnalyzeDurationDialog";
import { InputPanel } from "@/components/mame/panels/InputPanel";
import { ParameterPanel } from "@/components/mame/panels/ParameterPanel";
import { WellSelectionPanel } from "@/components/mame/panels/WellSelectionPanel";
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
  const analyzeStage = useMameAppStore((s) => s.analyzeStage);
  const analyzeStartedAt = useMameAppStore((s) => s.analyzeStartedAt);
  // Written only where a run applies its response; cleared at run start and on
  // cancel/failure. So a null -> number edge is exactly one finished run.
  const analyzeDurationMs = useMameAppStore((s) => s.analyzeDurationMs);
  const validationErrors = useMameAppStore((s) => s.validationErrors);
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  // "A run finished and its response was applied" marker. `summary` is written
  // only from an analyze response (run or restored snapshot) and cleared by
  // Clear/reset, so it separates "not run yet" from "ran and produced nothing".
  // Those two states used to render the same blank 2.2 view.
  const analysisCompleted = useMameAppStore((s) => s.summary !== null);
  const zeroResult = analysisCompleted && !hasResults && !isAnalyzing;
  const cancelAnalysis = useMameAppStore((s) => s.cancelAnalysis);
  const validateInputs = useMameAppStore((s) => s.validateInputs);
  const openExport = useMameAppStore((s) => s.openExport);
  const runAnalysis = useMameAppStore((s) => s.runAnalysis);
  const canRun = useMameAppStore(selectCanRun);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const wasAnalyzingRef = useRef(isAnalyzing);
  const [plateExpanded, setPlateExpanded] = useState(false);
  // Duration popup. Held in view state (not the store) so dismissing it does
  // not erase the run record, and so a remount does not re-open it.
  const [durationPopupMs, setDurationPopupMs] = useState<number | null>(null);
  const prevDurationRef = useRef<number | null>(analyzeDurationMs);
  const reviewContainerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!plateExpanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPlateExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [plateExpanded]);

  useEffect(() => {
    const wasAnalyzing = wasAnalyzingRef.current;
    wasAnalyzingRef.current = isAnalyzing;
    // Advance on completion, not on "produced verdicts". A zero-verdict run is
    // still a finished run and its outcome is stated on 2.2; gating on
    // hasResults left the user on 2.1 with a bare "Analysis complete".
    if (
      subStep === "analyze.inputs" &&
      wasAnalyzing &&
      !isAnalyzing &&
      analysisCompleted &&
      validationErrors.length === 0
    ) {
      setMameSubStep("analyze.review");
    }
  }, [analysisCompleted, isAnalyzing, setMameSubStep, subStep, validationErrors.length]);

  // Report how long the finished run took. Keyed on the store's null -> number
  // edge, so it fires once per run and never on a re-render or a remount that
  // merely observes an already-reported duration.
  //
  // Suppressed for a zero-verdict run: v0.15.3 answers that case with
  // EmptyAnalysisNotice, and a modal over that notice would make the user
  // dismiss the less useful message to reach the more useful one. The elapsed
  // time is also the least of what such a run needs to say.
  useEffect(() => {
    const prev = prevDurationRef.current;
    prevDurationRef.current = analyzeDurationMs;
    if (prev !== null || analyzeDurationMs === null) return;
    if (!hasResults) return;
    setDurationPopupMs(analyzeDurationMs);
  }, [analyzeDurationMs, hasResults]);

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
          {/* 복원 후 되찾지 못한 외부 입력. 해소될 때까지 남는다. */}
          <MissingInputsBanner />
          {/* Progress 및 상태 */}
          <div className="space-y-1 px-1">
            {(() => {
              // A finished run with nothing to show must not read as success.
              const statusLine = zeroResult
                ? t("mame.analyze.zeroResult.statusLine")
                : analyzeMessage || (isAnalyzing ? t("mameSidebar.statusAnalyzing") : canRun ? t("mameSidebar.statusReady") : t("mameSidebar.statusIncomplete"));
              return (
                <div className="truncate text-body font-medium text-foreground" aria-live="polite" title={statusLine}>
                  {statusLine}
                </div>
              );
            })()}
            {isAnalyzing && (
              <Progress
                value={analyzeProgress}
                className="mt-1.5 h-1"
                aria-label={t("mameSidebar.analysisProgressAria", { percent: analyzeProgress })}
              />
            )}
            {isAnalyzing && analyzeCurrent !== null && (
              <p className="mt-1 text-caption text-muted-foreground" aria-live="polite">
                {analyzeTotal !== null
                  ? `${analyzeCurrent.toLocaleString()} / ${analyzeTotal.toLocaleString()}`
                  : `${analyzeCurrent}%`}
              </p>
            )}
            {isAnalyzing && analyzeStage && (
              <p className="mt-0.5 text-caption text-muted-foreground" aria-live="polite">
                {t(`mame.analyze.phase.${analyzeStage}`, { defaultValue: analyzeStage })}
              </p>
            )}
            {isAnalyzing && analyzeStartedAt !== null && analyzeProgress > 0 && (
              <p className="mt-0.5 text-caption text-muted-foreground" aria-live="polite">
                <span className="font-medium">{t("mame.analyze.etaLabel")}:</span>{" "}
                {computeEtaFromElapsed(analyzeProgress, analyzeStartedAt, t)}
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

          {/* Before the errors above in importance, after them in position: a
              plate disagreement is not a validation error (the backend leaves
              `valid` true) but it is the one finding that makes an otherwise
              clean run answer the wrong question. */}
          <PlateOrderNotice />

          {/* Which replicates the results on screen were scored on. Next to the
              plate notice because both answer "what plate is this?": one about
              which plate the workbook describes, one about how many copies of
              it the run actually covered. */}
          <ReplicateModeNotice />

          {/* Whose engine produced the verdicts currently on screen. Rendered on
              both 2.1 and 2.2 (one sub-step is on screen at a time): the inputs
              step is where a re-run starts, and the review step is where the
              restored verdicts are actually read. */}
          <RestoredResultNotice onRunRequest={onRunRequest} />


          {zeroResult && <EmptyAnalysisNotice />}

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
          {/* An old project's sample map, once it has been compared against the
              layout that replaced it. A disagreement is a validation error and
              shows with the others; this is the other outcome. */}
          <LegacySampleMapNotice />
          <WellSelectionPanel />
          <ParameterPanel />
        </div>
      );
      break;
    case "analyze.review":
      // A finished run with no verdict has nothing to put in the table, the
      // plate map, or the chart. Say why instead of rendering three empty
      // panels that look exactly like the pre-run view.
      if (zeroResult) {
        mainContent = (
          <div className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-1">
            <EmptyAnalysisNotice />
            {/* The zero-verdict view is where "why does this look wrong" is
                actually asked, so the reuse line belongs here too, not only on
                the populated one. */}
            <DemuxResumeNotice />
            {/* Mounted here for the same reason as the panel below: this branch
                replaces the whole review. A run that produced no verdict is
                also where "which reference did it read" is the first question,
                so the one screen that can answer it must not be the one screen
                that drops it. */}
            <ReferenceResolutionNotice />
            {/* A run that produced no verdict is exactly where the stray-read
                view earns its place: the reads went somewhere, and the matrix
                is the only thing that can say whether it was a well nobody
                pipetted. Mounted here as well as on the normal review because
                this branch replaces the whole review, panels included. */}
            <ContaminationPanel />
          </div>
        );
        break;
      }
      // Unified review: left = Summary + Verdict table, right = Plate (top) + per-plate verdict chart (bottom).
      // The only RunHealthPanel on this screen is the one below, and it renders
      // the verdict breakdown alone. The other sections (file-size / throughput
      // / pore-yield / barcode / cross-talk) live in the QC inspector; 2.1 has
      // no RunHealthPanel to reach them from, whatever this comment used to say.
      mainContent = (
        <div className="relative flex flex-col" ref={reviewContainerRef}>
          {/* First of everything on this screen, and only when the run could not
              have worked. A shallow plate is not a detail about how the run went,
              it is the reason the numbers below it do not mean anything, and it
              has to be unreadable-past rather than one notice among several.
              Silent for every run that cleared the depth floor. */}
          <RunQualityNotice />
          {/* Above the softer cluster/autosave notices: a suspect mapping is a
              judgment about whether this whole result can be trusted, not a
              detail about how it ran. */}
          <MappingIntegrityAlert />
          {/* Which reference the verdicts above were actually scored against.
              On the review screen rather than the inputs screen because it is
              an answer about a finished run, not a property of the file in the
              form: the slice exists only once a run has cut it. */}
          <ReferenceResolutionNotice />
          {/* Above the off-layout notice because it answers the prior
              question: which of the drafted variants this run did not put on
              the plate at all. Those have no verdict, so on this screen they
              are an absence indistinguishable from a well the campaign never
              had, and the review screen is where a restored project can still
              be asked what was left out. */}
          <ExcludedOccupantsNotice />
          <OffLayoutRecordsNotice />
          {/* Beside the off-layout notice because the two answer the same
              question from opposite ends: that one counts SCORED records from
              undeclared wells, this one counts READS on barcode combinations
              nobody pipetted, including the ones that never became a record. */}
          <ContaminationPanel />
          <PlateClusterAlert />
          <RestoredResultNotice onRunRequest={onRunRequest} />
          {/* Below the notices that judge the result, above the panels that
              show it: how much of what follows was reseeded from a previous
              run in the same export folder. Renders nothing when nothing was
              reused. */}
          <DemuxResumeNotice />
          {/* The right column decides how tall this row is, because both panels
              in it draw at the size their content needs: the whole plate, and
              the whole breakdown. Sizing them to the window is what kept showing
              a plate cropped at row D with a scrollbar over the rest.

              The left column takes that height rather than adding to it. Its
              contents are absolutely positioned, so the verdict table (up to 96
              rows, virtualised, with its own scroll container) reports no
              intrinsic height and cannot stretch the row. The operator sees
              roughly a right-column worth of rows and scrolls the table for the
              rest, while the page carries one scrollbar for everything else.

              Below `lg` the columns stack and the absolute trick has no row to
              borrow from, so the table gets an explicit viewport-relative height
              instead. */}
          <div className="mt-3 grid gap-3 lg:grid-cols-2 lg:items-stretch">
            <div className="relative h-[70vh] lg:h-auto">
              <div className="absolute inset-0 flex flex-col gap-3">
                <div className="flex-shrink-0">
                  <SummaryRow />
                </div>
                <DataPanel
                  title={t("mame.appLayout.verdictTableTitle")}
                  className="min-h-0 flex-1"
                >
                  <VerdictTable />
                </DataPanel>
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <DataPanel title={t("mame.appLayout.platePlanTitle")} autoHeight>
                <div
                  role="region"
                  aria-label={t("mame.plateView.expandedRegionAriaLabel")}
                  className={plateExpanded ? "absolute inset-0 z-40 bg-background overflow-auto" : undefined}
                >
                  <PlateView
                    expanded={plateExpanded}
                    autoHeight={!plateExpanded}
                    onToggleExpand={() => setPlateExpanded((v) => !v)}
                  />
                </div>
              </DataPanel>
              <DataPanel title={t("mame.appLayout.efficiencyChartTitle")} autoHeight>
                {runHealth !== null ? (
                  <RunHealthPanel
                    health={runHealth}
                    sections={["verdict-breakdown"]}
                    showSectionHeadings={false}
                  />
                ) : (
                  <div className="p-4 text-caption text-muted-foreground">
                    {t("mameSidebar.statusIncomplete")}
                  </div>
                )}
              </DataPanel>
            </div>
          </div>
        </div>
      );
      break;
    default:
      mainContent = null;
  }

  return (
    <>
    <AnalyzeDurationDialog
      durationMs={durationPopupMs}
      onClose={() => setDurationPopupMs(null)}
    />
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
    </>
  );
}
