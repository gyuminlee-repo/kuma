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

import { AlertCircle, Download, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import { MissingInputsBanner } from "@/components/mame/panels/MissingInputsBanner";
import { computeEtaFromElapsed } from "@/lib/eta";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { useContentFitSplit } from "@/hooks/useContentFitSplit";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { selectCanRun } from "@/store/mame/selectors";
import { DataPanel } from "@/components/ui/Panel";
import { SummaryRow } from "@/components/mame/widgets/SummaryRow";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { RunHealthPanel } from "@/components/mame/widgets/RunHealthPanel";
import { PlateClusterAlert } from "@/components/mame/widgets/PlateClusterAlert";
import { MappingIntegrityAlert } from "@/components/mame/widgets/MappingIntegrityAlert";
import { EmptyAnalysisNotice } from "@/components/mame/widgets/EmptyAnalysisNotice";
import { PlateOrderNotice } from "@/components/mame/widgets/PlateOrderNotice";
import { JanusAutosaveNotice } from "@/components/mame/widgets/JanusAutosaveNotice";
import { AnalyzeDurationDialog } from "@/components/mame/dialogs/AnalyzeDurationDialog";
import { JanusMappingDialog } from "@/components/mame/dialogs/JanusMappingDialog";
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
  const analyzeStage = useMameAppStore((s) => s.analyzeStage);
  const analyzeStartedAt = useMameAppStore((s) => s.analyzeStartedAt);
  const janusSettings = useMameAppStore((s) => s.janusSettings);
  const setJanusSettings = useMameAppStore((s) => s.setJanusSettings);
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
  // Janus instrument settings, reachable from the inputs step. Local state: the
  // step 3 CTA owns its own instance of the same dialog, and only one of the two
  // steps is on screen at a time, so no shared open flag is needed.
  const [janusSettingsOpen, setJanusSettingsOpen] = useState(false);
  const prevDurationRef = useRef<number | null>(analyzeDurationMs);
  const reviewContainerRef = useRef<HTMLDivElement>(null);
  // Plate map over verdict breakdown, sized by what each one needs. minSize here
  // matches the two Panels below, so a fit can never propose a share the group
  // would refuse.
  const reviewSplit = useContentFitSplit({
    minFirst: 18,
    minSecond: 30,
    autoSaveId: "mame.analyze.review.vsplit.v2",
    // Verdict count changes the plate map, run health changes the breakdown.
    deps: [subStep, hasResults, runHealth !== null],
  });
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
            <div className="truncate text-body font-medium text-foreground" aria-live="polite">
              {/* A finished run with nothing to show must not read as success. */}
              {zeroResult
                ? t("mame.analyze.zeroResult.statusLine")
                : analyzeMessage || (isAnalyzing ? t("mameSidebar.statusAnalyzing") : canRun ? t("mameSidebar.statusReady") : t("mameSidebar.statusIncomplete"))}
            </div>
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

          {/* The run writes its pick list on its own; whether it did is part of
              the run's outcome, not a detail of the export dialog. */}
          <JanusAutosaveNotice />

          {/* Transfer volume, the one instrument value nothing can derive: how
              much of a cell stock to move is an experimental condition, unlike
              the deck numbers (taken from the plates of the run) and the liquid
              class (left blank when unset). It sits here rather than only in the
              dialog because the run writes the instrument sheet on its own, and
              the shipped 100 µL is an assumption with no lab source. */}
          <div className="space-y-1">
            <label
              htmlFor="mame-janus-volume"
              className="text-caption font-medium text-muted-foreground"
            >
              {t("mame.analyze.janusVolume.label")}
            </label>
            <input
              id="mame-janus-volume"
              type="number"
              min={0}
              step="any"
              value={janusSettings.volume}
              onChange={(e) => {
                const parsed = Number.parseFloat(e.target.value);
                if (Number.isFinite(parsed) && parsed > 0) {
                  setJanusSettings({ ...janusSettings, volume: parsed });
                }
              }}
              className="h-control w-full rounded-control border border-border bg-background px-2 text-caption"
            />
            <p className="text-caption text-muted-foreground">
              {t("mame.analyze.janusVolume.hint")}
            </p>
          </div>

          {/* Janus instrument settings. Optional, and never a run gate: the run
              writes both files without any of these values. Only an entry point
              lives here (the dialog carries deck preview, row preview and the
              export), so the inputs step stays a step about inputs. Enabled
              before a run too, so the values can be prepared in advance. */}
          <div className="space-y-1">
            <Button
              variant="outline"
              size="sm"
              className="h-control w-full gap-1.5 rounded-control text-caption"
              onClick={() => setJanusSettingsOpen(true)}
              aria-label={t("mame.analyze.janusSettings.openAriaLabel")}
            >
              <Settings2 size={12} aria-hidden="true" />
              {t("mame.analyze.janusSettings.open")}
            </Button>
            <p className="text-caption text-muted-foreground">
              {t("mame.analyze.janusSettings.hint")}
            </p>
          </div>
          <JanusMappingDialog
            open={janusSettingsOpen}
            onOpenChange={setJanusSettingsOpen}
          />

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
          <div className="flex h-full min-h-0 flex-col overflow-auto p-1">
            <EmptyAnalysisNotice />
          </div>
        );
        break;
      }
      // Unified review: left = Summary + Verdict table, right = Plate (top) + per-plate verdict chart (bottom).
      // Other RunHealth sections (file-size/throughput/pore-yield/barcode/cross-talk) are still reachable from
      // analyze.inputs's RunHealthPanel and the QC inspector; not duplicated here per PI spec slide 6.
      mainContent = (
        <div className="flex h-full min-h-0 flex-col relative" ref={reviewContainerRef}>
          {/* Above the softer cluster/autosave notices: a suspect mapping is a
              judgment about whether this whole result can be trusted, not a
              detail about how it ran. */}
          <MappingIntegrityAlert />
          <PlateClusterAlert />
          <JanusAutosaveNotice />
          <div className="flex-1 min-h-0">
          <PanelGroup direction="horizontal" autoSaveId="mame.analyze.review.split">
            <Panel defaultSize={50} minSize={25}>
              <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
                <div className="flex-shrink-0">
                  <SummaryRow />
                </div>
                <DataPanel title={t("mame.appLayout.verdictTableTitle")} className="flex-1 min-h-[240px]">
                  <VerdictTable />
                </DataPanel>
              </div>
            </Panel>
            <PanelResizeHandle
              className="w-2 bg-border hover:bg-border/70 transition-colors"
              aria-label={t("mame.appLayout.verdictTableTitle")}
            />
            <Panel defaultSize={50} minSize={25}>
              {/* Split by what the two panels need. A fixed ratio gave the plate
                  map the smaller share on every window size (381 px of grid
                  hidden at 1920x1080, 442 px at 2560x1440) while the breakdown
                  below it had room to spare; see useContentFitSplit. */}
              <PanelGroup
                ref={reviewSplit.groupRef}
                direction="vertical"
                autoSaveId="mame.analyze.review.vsplit.v2"
              >
                <Panel defaultSize={34} minSize={18}>
                  {/* PlateView keeps its own scroll containers (the grid area
                      and the selected-well aside), so the panel body stays
                      unscrolled, a second scrollbar here would nest. */}
                  <div ref={reviewSplit.firstRef} className="h-full min-h-0">
                    <DataPanel title={t("mame.appLayout.platePlanTitle")} className="h-full min-h-0">
                      <div
                        role="region"
                        aria-label={t("mame.plateView.expandedRegionAriaLabel")}
                        className={plateExpanded ? "absolute inset-0 z-40 bg-background overflow-auto" : "h-full"}
                      >
                        <PlateView expanded={plateExpanded} onToggleExpand={() => setPlateExpanded((v) => !v)} />
                      </div>
                    </DataPanel>
                  </div>
                </Panel>
                <PanelResizeHandle
                  className="h-2 bg-border hover:bg-border/70 transition-colors"
                  onDragging={reviewSplit.onDragging}
                />
                <Panel defaultSize={66} minSize={30}>
                  <div ref={reviewSplit.secondRef} className="h-full min-h-0">
                  {/* RunHealthPanel just lays its sections out, so whatever it
                      renders has to fit or be reachable by scrolling: the user
                      can drag the splitter above down to well under the chart's
                      natural height. `min-h-0` (not a px floor) because the
                      panel really can be shorter than the content. */}
                  <DataPanel
                    title={t("mame.appLayout.efficiencyChartTitle")}
                    className="h-full min-h-0"
                    scrollBody
                  >
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
