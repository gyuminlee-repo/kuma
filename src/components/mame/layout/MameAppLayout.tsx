import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { AppShell } from "@/components/shell/AppShell";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { resetMameAll } from "@/store/mame/resetAll";
import { useKumaProject } from "@/state/projectContext";
import { selectCanRun } from "@/store/mame/selectors";
import { useMameSidecar } from "@/hooks/mame/useMameSidecar";
import { initActivityStore } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { tryHandleManifestDrop, tryHandleTwoManifestsDrop, verifyInputs, type InputVerifyResult } from "@/lib/reRun";
import { type RunManifest } from "@/lib/runManifest";
import { ReRunManifestDialog } from "@/components/dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "@/components/dialogs/ManifestDiffDialog";
import { ClearConfirmDialog } from "@/components/dialogs/ClearConfirmDialog";
import { ExportDialog } from "../dialogs/ExportDialog";
import { NativeBarcodeConfirmDialog } from "../dialogs/NativeBarcodeConfirmDialog";
import { WellLayoutConfirmDialog } from "../dialogs/WellLayoutConfirmDialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { startDeadlockWatch, DEADLOCK_THRESHOLD_MS } from "@/lib/deadlockDetector";
import { getLastProgressAt } from "@/lib/ipc-mame";
import { PreflightDialog } from "@/components/dialogs/PreflightDialog";
import { OverwriteConfirmDialog } from "@/components/dialogs/OverwriteConfirmDialog";
import { runPreflightCheck } from "@/lib/preflight";
import type { PreflightResult } from "@/lib/preflight";
import { useMainZoom } from "@/hooks/useMainZoom";
import { MenuBar } from "./MenuBar";
import { WhatsNewDialog } from "@/components/dialogs/WhatsNewDialog";
import { StatusBar } from "./StatusBar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SetupStepView } from "@/components/mame/steps/SetupStepView";
import { AnalyzeStepView } from "@/components/mame/steps/AnalyzeStepView";
import { ActivityStepView } from "@/components/mame/steps/ActivityStepView";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import type { MamePhase } from "@/store/mame/slices/phaseSlice";
import { MameWorkflowRail } from "./MameWorkflowRail";
import { MameInspectorContent, useMameInspectorMeta } from "./MameInspectorContent";
import { useMameDrawerProps } from "./MameDrawerContent";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { ContextHeader } from "@/components/widgets/ContextHeader";
import { DrawerStrip } from "@/components/widgets/DrawerStrip";
import { JanusMappingDialog } from "@/components/mame/dialogs/JanusMappingDialog";
import { useMameAutosave } from "@/hooks/useMameAutosave";

// Activity store는 RoundStore를 주입받아 초기화 (lazy singleton).
// MameAppLayout 모듈 로드 시 단 한 번만 실행.
initActivityStore(useRoundStore);

const SEQUENCE_EXTENSIONS = new Set([".fa", ".fasta", ".fna"]);
const XLSX_EXTENSIONS = new Set([".xlsx"]);

// ContextHeader 제목/부제 — sub-step별 i18n 키 매핑
const CONTEXT_TITLE_KEYS: Record<MameSubStepId, { title: string; subtitle: string }> = {
  "setup.files":        { title: "mame.setup.files.contextTitle",         subtitle: "mame.setup.files.contextSubtitle" },
  "setup.design":       { title: "mame.setup.design.contextTitle",        subtitle: "mame.setup.design.contextSubtitle" },
  "analyze.inputs":     { title: "mame.qc.inputs.contextTitle",           subtitle: "mame.qc.inputs.contextSubtitle" },
  "analyze.review":     { title: "mame.qc.review.contextTitle",           subtitle: "mame.qc.review.contextSubtitle" },
  // Legacy ids (Task #12 통합 후 redirect 진입 표시용)
  "analyze.verdict":    { title: "mame.qc.review.contextTitle",           subtitle: "mame.qc.review.contextSubtitle" },
  "analyze.plate":      { title: "mame.qc.review.contextTitle",           subtitle: "mame.qc.review.contextSubtitle" },
  "activity.ingest":    { title: "mame.activity.ingest.contextTitle",     subtitle: "mame.activity.ingest.contextSubtitle" },
  "activity.mergeExport": { title: "mame.activity.mergeExport.contextTitle", subtitle: "mame.activity.mergeExport.contextSubtitle" },
};

export function MameAppLayout() {
  const { t } = useTranslation();
  const project = useKumaProject();
  // F3: kuro와 동일한 localStorage "kuma.mainZoom" 공유 — Ctrl+wheel / Ctrl+=/−/0
  const zoom = useMainZoom();
  const { status, retry } = useMameSidecar();
  const { flushMameAutosave } = useMameAutosave();
  // Clear All triggers full workspace reset (slices + manifest artifacts).
  const handleClearAll = useCallback(() => {
    void resetMameAll();
  }, []);
  const runHealth = useMameAppStore((s) => s.runHealth);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const mamePhase = useMameAppStore((s) => s.mamePhase);
  const setMamePhase = useMameAppStore((s) => s.setMamePhase);
  const [isDragOver, setIsDragOver] = useState(false);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  // §1 Dead-lock 감지 모달 상태
  const [deadlockOpen, setDeadlockOpen] = useState(false);

  // §12 Reproducibility: manifest re-run 모달 상태
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);
  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);
  const reRunVerifyRef = useRef<InputVerifyResult | null>(null);
  const [reRunStatusMsg, setReRunStatusMsg] = useState("");

  // §12 Reproducibility: manifest diff 모달 상태
  const [diffManifestA, setDiffManifestA] = useState<RunManifest | null>(null);
  const [diffManifestB, setDiffManifestB] = useState<RunManifest | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  // §19 Performance Guardrails: pre-flight check 결과 상태
  const [preflightResult, setPreflightResult] = useState<{
    result: PreflightResult;
    pendingAction: () => void;
  } | null>(null);

  /**
   * Run 트리거 — pre-flight 검사 후 분석 실행.
   * AnalyzeStepView와 키보드 단축키 모두 이 콜백을 사용.
   */
  const tryRunAnalysis = useCallback(() => {
    const s = useMameAppStore.getState();
    if (!selectCanRun(s)) return;
    void runPreflightCheck({ sidecarStatus: status, requiresNetwork: false }).then(
      (pfResult) => {
        const actualRun = () => {
          void flushMameAutosave().then(() => useMameAppStore.getState().runAnalysis());
        };
        if (!pfResult.ok || pfResult.warnings.length > 0) {
          setPreflightResult({ result: pfResult, pendingAction: actualRun });
        } else {
          actualRun();
        }
      },
    );
  }, [flushMameAutosave, status]);

  // §1 Dead-lock 감지: analysis 진행 중 DEADLOCK_THRESHOLD_MS 초과 시 모달 표시
  useEffect(() => {
    if (!isAnalyzing) return;
    return startDeadlockWatch({
      getLastProgressAt,
      onDeadlock: () => setDeadlockOpen(true),
    });
  }, [isAnalyzing]);

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === "enter" || event.payload.type === "over") {
          setIsDragOver(true);
        } else if (event.payload.type === "leave") {
          setIsDragOver(false);
        } else if (event.payload.type === "drop") {
          setIsDragOver(false);
          const { paths } = event.payload;

          // §12 Reproducibility: 2개 manifest 동시 드롭 → diff 흐름 우선
          void tryHandleTwoManifestsDrop(paths).then(async (twoResult) => {
            if (twoResult.handled) {
              if (twoResult.error) {
                setReRunStatusMsg(t("mame.appLayout.manifestLoadFailed", { err: twoResult.error }));
                return;
              }
              if (twoResult.manifestA && twoResult.manifestB) {
                setDiffManifestA(twoResult.manifestA);
                setDiffManifestB(twoResult.manifestB);
                setDiffOpen(true);
              }
              return;
            }

            // §12 Reproducibility: 단일 manifest → re-run 흐름
            void tryHandleManifestDrop(paths).then(async (result) => {
              if (!result.handled) {
                // 기존 파일 처리 흐름
                for (const filePath of paths) {
                  const ext = filePath.slice(filePath.lastIndexOf(".")).toLowerCase();
                  if (SEQUENCE_EXTENSIONS.has(ext)) {
                    useMameAppStore.getState().setReferencePath(filePath);
                    break;
                  }
                  if (XLSX_EXTENSIONS.has(ext)) {
                    window.dispatchEvent(
                      new CustomEvent("kuma:mame-xlsx-dropped", { detail: { path: filePath } }),
                    );
                    useMameAppStore.getState().setExpectedPath(filePath);
                    break;
                  }
                }
                return;
              }

              if (result.error) {
                setReRunStatusMsg(t("mame.appLayout.manifestLoadFailed", { err: result.error }));
                return;
              }

              if (result.manifest) {
                const verify = await verifyInputs(result.manifest);
                reRunVerifyRef.current = verify;
                setReRunVerify(verify);
                setReRunManifest(result.manifest);
              }
            });
          });
        }
      })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch((err) => {
        console.warn("[AppLayout] onDragDropEvent failed:", err);
      });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (!(e.target instanceof Element)) return;
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const s = useMameAppStore.getState();
      switch (e.key.toLowerCase()) {
        case "e":
          e.preventDefault();
          if (s.verdicts.length > 0) s.openExport();
          break;
        case "d":
          e.preventDefault();
          tryRunAnalysis();
          break;
        case "enter":
          e.preventDefault();
          if (!s.isAnalyzing) tryRunAnalysis();
          break;
        case "r":
          // Cmd/Ctrl+Shift+R: Reset All (확인 다이얼로그 경유)
          if (!e.shiftKey) return;
          e.preventDefault();
          setClearConfirmOpen(true);
          break;
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [project, tryRunAnalysis]);

  // 현재 sub-step 기반 ContextHeader 메타
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
  const contextMeta = CONTEXT_TITLE_KEYS[currentSubStep];

  // Inspector 메타 (제목/부제)
  const inspectorMeta = useMameInspectorMeta();

  // DrawerStrip props
  const drawerProps = useMameDrawerProps();

  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);

  // JANUS dialog 상태 — Layout이 단독 소유. MenuBar와 CTA 버튼이 같은 setter 공유.
  const [janusOpen, setJanusOpen] = useState(false);

  // 단일 Step 3(activity.ingest)에서 JANUS CTA 표시. mergeExport는 legacy redirect id.
  const showJanusCta =
    currentSubStep === "activity.ingest" || currentSubStep === "activity.mergeExport";

  return (
    <Tabs
      value={mamePhase}
      onValueChange={(v) => setMamePhase(v as MamePhase)}
      className="flex h-full flex-col"
    >
      <AppShell
        tool="mame"
        titlebar={
          <MenuBar
            onClearRequest={() => setClearConfirmOpen(true)}
            onRunRequest={tryRunAnalysis}
            onJanusOpen={() => setJanusOpen(true)}
          />
        }
        subnav={
          <div className="flex items-center w-full mx-3 mt-2">
            <TabsList className="shrink-0 w-fit">
              <TabsTrigger value="setup" title={t("mame.appLayout.barcodeSetupTabTitle")}>
                {t("mame.appLayout.barcodeSetupTab")}
              </TabsTrigger>
              <TabsTrigger value="analyze" title={t("mame.appLayout.analyzeTabTitle")}>
                {t("mame.appLayout.analyzeTab")}
              </TabsTrigger>
              <TabsTrigger value="activity" title={t("mame.appLayout.activityTabTitle")}>
                {t("mame.appLayout.activityTab")}
              </TabsTrigger>
            </TabsList>
            <Button
              variant="outline"
              size="sm"
              className="ml-auto mr-3 h-7 rounded-control text-caption"
              onClick={() => setClearConfirmOpen(true)}
              disabled={isAnalyzing}
            >
              {t("appLayout.clearAll")}
            </Button>
          </div>
        }
        sidebar={<MameWorkflowRail />}
        inspector={
          <InspectorPanel title={inspectorMeta.title} subtitle={inspectorMeta.subtitle}>
            <MameInspectorContent />
          </InspectorPanel>
        }
        main={
          <div
            id="major-step-main"
            className="flex flex-col flex-1 min-h-0 min-w-0 overflow-hidden"
            style={{ zoom }}
          >
            {/* ContextHeader — 현재 화면 제목/부제 */}
            <ContextHeader
              title={t(contextMeta.title)}
              subtitle={t(contextMeta.subtitle)}
            />

            {/* Phase 1: Barcode Setup */}
            <TabsContent value="setup" className="flex-1 min-h-0 overflow-hidden mt-0">
              <SetupStepView />
            </TabsContent>

            {/* Phase 2: Analyze */}
            <TabsContent value="analyze" className="flex-1 min-h-0 overflow-hidden mt-0">
              <AnalyzeStepView
                runHealth={runHealth}
                onRunRequest={tryRunAnalysis}
                onClearRequest={() => setClearConfirmOpen(true)}
              />
            </TabsContent>

            {/* Phase 3: Activity */}
            <TabsContent value="activity" className="flex-1 min-h-0 overflow-hidden mt-0">
              <ActivityStepView />
              {/* Merge & Export 화면 JANUS CTA (GAP P1) — MenuBar가 dialog 소유 */}
              {showJanusCta && (
                <div className="shrink-0 border-t border-border px-4 py-3">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    onClick={() => setJanusOpen(true)}
                    disabled={!hasResults}
                    aria-label={t("mame.activity.mergeExport.openJanusExportAriaLabel")}
                  >
                    {t("mame.activity.mergeExport.openJanusExport")}
                  </Button>
                </div>
              )}
            </TabsContent>

            {/* DrawerStrip — 하단 3-슬롯 */}
            <DrawerStrip
              left={drawerProps.left}
              center={drawerProps.center}
              right={drawerProps.right}
            />
          </div>
        }
        statusbar={<StatusBar sidecarStatus={status} onRetry={retry} />}
        isDragOver={isDragOver}
        className="h-full"
      >
        <WhatsNewDialog />

        {/* §19 Performance Guardrails: pre-flight check 결과 모달 */}
        {preflightResult && (
          <PreflightDialog
            open={preflightResult !== null}
            result={preflightResult.result}
            onContinue={() => {
              const action = preflightResult.pendingAction;
              setPreflightResult(null);
              action();
            }}
            onCancel={() => setPreflightResult(null)}
          />
        )}

        {/* §1 Recovery: Dead-lock 감지 모달 */}
        <Dialog open={deadlockOpen} onOpenChange={setDeadlockOpen}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>{t("mame.appLayout.deadlockTitle")}</DialogTitle>
              <DialogDescription>
                {t("mame.appLayout.deadlockDescription", { seconds: DEADLOCK_THRESHOLD_MS / 1000 })}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setDeadlockOpen(false)}>
                {t("mame.appLayout.deadlockWait")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-error border-error/40 hover:bg-error/8"
                onClick={() => {
                  void useMameAppStore.getState().cancelAnalysis();
                  setDeadlockOpen(false);
                }}
              >
                {t("mame.appLayout.deadlockReset")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <ExportDialog />
        <NativeBarcodeConfirmDialog />
        <WellLayoutConfirmDialog />
        <ClearConfirmDialog
          open={clearConfirmOpen}
          onOpenChange={setClearConfirmOpen}
          onConfirm={handleClearAll}
        />

        {/* §12 Reproducibility: re-run status 표시 (4초 자동 소멸) */}
        {reRunStatusMsg && (
          <div
            role="status"
            aria-live="polite"
            aria-atomic="true"
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 rounded-md border border-border bg-card px-4 py-2 text-sm shadow-md text-foreground"
            onAnimationEnd={() => setReRunStatusMsg("")}
          >
            {reRunStatusMsg}
          </div>
        )}

        {/* §12 Reproducibility: manifest re-run 확인 모달 */}
        <ReRunManifestDialog
          open={reRunManifest !== null}
          manifest={reRunManifest}
          verifyResult={reRunVerify}
          onClose={() => {
            setReRunManifest(null);
            setReRunVerify(null);
            reRunVerifyRef.current = null;
          }}
          onStatusMessage={(msg) => {
            setReRunStatusMsg(msg);
            setTimeout(() => setReRunStatusMsg(""), 4000);
          }}
        />

        {/* §12 Reproducibility: manifest diff 모달 */}
        <ManifestDiffDialog
          open={diffOpen}
          manifestA={diffManifestA}
          manifestB={diffManifestB}
          onClose={() => {
            setDiffOpen(false);
            setDiffManifestA(null);
            setDiffManifestB(null);
          }}
        />

        {/* §5 Output Persistence: 덮어쓰기 confirm */}
        <OverwriteConfirmDialog />

        {/* JANUS CTA 진입 dialog — main pane "Open JANUS export..." 버튼 전용 (GAP P1) */}
        <JanusMappingDialog open={janusOpen} onOpenChange={setJanusOpen} />
      </AppShell>
    </Tabs>
  );
}
