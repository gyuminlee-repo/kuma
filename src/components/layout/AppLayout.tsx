import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { classifyError } from "@/lib/errorClassifier";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AppShell } from "../shell/AppShell";
import { useAppStore } from "../../store/appStore";
import { useSidecar } from "../../hooks/useSidecar";
import { useKumaProject } from "../../state/projectContext";
import { useRunDesign } from "../../hooks/useRunDesign";
import { tryHandleManifestDrop, tryHandleTwoManifestsDrop, verifyInputs, type InputVerifyResult } from "@/lib/reRun";
import { type RunManifest } from "@/lib/runManifest";
import { ReRunManifestDialog } from "../dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "../dialogs/ManifestDiffDialog";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { MenuBar } from "./MenuBar";
import { MajorSubnav, type MajorNavItem } from "./MajorSubnav";
import { MajorStepView } from "../steps/MajorStepView";
import { SequenceViewer } from "@/components/widgets/SequenceViewer";
import { StatusBar } from "./StatusBar";
import { WhatsNewDialog } from "../dialogs/WhatsNewDialog";
import { NetworkConsentDialog } from "../dialogs/NetworkConsentDialog";
import { OverwriteConfirmDialog } from "../dialogs/OverwriteConfirmDialog";
import { handleOpenSequence } from "./export-handlers";
import { startDeadlockWatch } from "@/lib/deadlockDetector";
import { getLastProgressAt } from "@/lib/ipc-kuro";
import { MAJOR_ORDER } from "@/store/slices/navigationSlice";
import { useMainZoom } from "@/hooks/useMainZoom";
import {
  KuroWorkflowRail,
  KuroDrawerStrip,
  KuroInspector,
} from "./KuroChrome";

const SEQUENCE_EXTENSIONS = new Set([".gb", ".gbk", ".gbff", ".dna", ".fa", ".fasta"]);
const CSV_EXTENSIONS = new Set([".csv"]);
const LazyDesignReport = lazy(async () => import("../dialogs/DesignReport").then((m) => ({ default: m.DesignReport })));
const LazyBenchmarkDialog = lazy(async () => import("../dialogs/BenchmarkDialog").then((m) => ({ default: m.BenchmarkDialog })));

export function AppLayout() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const { status: sidecarStatus, retry: retrySidecar } = useSidecar();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const statusMessage = useAppStore((s) => s.statusMessage);
  // §4 네트워크 에러 분리 — statusMessage를 분류해 WifiOff 아이콘 표시
  const statusErrorKind = useMemo(() => {
    if (!statusMessage) return null;
    // 에러 키워드가 포함된 메시지에만 적용 (모든 status에 아이콘 붙이면 노이즈)
    if (!/fail|error|timeout|refused/i.test(statusMessage)) return null;
    return classifyError(statusMessage).kind;
  }, [statusMessage]);
  const loadPolymerases = useAppStore((s) => s.loadPolymerases);
  const showReport = useAppStore((s) => s.showReport);
  const showBenchmark = useAppStore((s) => s.showBenchmark);
  const loadNetworkConsentSettings = useAppStore((s) => s.loadNetworkConsentSettings);
  const loadSettings = useAppStore((s) => s.loadSettings);
  const [isDragOver, setIsDragOver] = useState(false);
  // §1 Dead-lock 감지 모달 상태
  const [deadlockOpen, setDeadlockOpen] = useState(false);

  // §12 Reproducibility: manifest re-run 모달 상태
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);
  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);
  const reRunVerifyRef = useRef<InputVerifyResult | null>(null);

  // §12 Reproducibility: manifest diff 모달 상태
  const [diffManifestA, setDiffManifestA] = useState<RunManifest | null>(null);
  const [diffManifestB, setDiffManifestB] = useState<RunManifest | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  // Shared Run Design logic (validation / preflight / flush / design)
  // Dialog state (sizeWarning, preflightResult) is owned by RunDesignAction, not here.
  const { run: tryRunDesign } = useRunDesign();

  // Navigation state for AppShell slot wiring
  const currentMajor = useAppStore((s) => s.currentMajor);

  // F3: main content zoom (Ctrl+wheel + Ctrl+=/−/0, persisted to localStorage)
  const zoom = useMainZoom();

  // Build MAJORS and SUBSTEPS arrays from navigationSlice constants
  const MAJORS: MajorNavItem[] = MAJOR_ORDER.map((id) => ({
    id,
    labelKey: `phaseC.majors.${id}`,
  }));

  useEffect(() => {
    loadNetworkConsentSettings();
  }, [loadNetworkConsentSettings]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (sidecarStatus === "ready") {
      void loadPolymerases();
    }
  }, [loadPolymerases, sidecarStatus]);

  // §1 Dead-lock 감지: design 진행 중 30초 progress 정적 시 모달 표시
  useEffect(() => {
    if (!isDesigning) return;
    return startDeadlockWatch({
      getLastProgressAt,
      onDeadlock: () => setDeadlockOpen(true),
    });
  }, [isDesigning]);

  // Item 6: Sync window title with project name
  useEffect(() => {
    const title = project?.name ? `kuma — ${project.name}` : "kuma";
    void getCurrentWindow().setTitle(title);
  }, [project?.name]);

  // File drop via Tauri webview API
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === "enter" || event.payload.type === "over") {
          setIsDragOver(true);
        } else if (event.payload.type === "leave") {
          setIsDragOver(false);
        } else if (event.payload.type === "drop") {
          setIsDragOver(false);
          const paths = event.payload.paths;

          // §12 Reproducibility: 2개 manifest 동시 드롭 → diff 흐름 우선
          void tryHandleTwoManifestsDrop(paths).then(async (twoResult) => {
            if (twoResult.handled) {
              if (twoResult.error) {
                useAppStore.setState({ statusMessage: t("appLayout.manifestLoadFailed", { error: twoResult.error }) });
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
                    useAppStore.getState().loadSequence(filePath);
                    break;
                  }
                  if (CSV_EXTENSIONS.has(ext)) {
                    useAppStore.getState().loadEvolveproCsv(filePath);
                    break;
                  }
                }
                return;
              }

              if (result.error) {
                useAppStore.setState({ statusMessage: t("appLayout.manifestLoadFailed", { error: result.error }) });
                return;
              }

              if (result.manifest) {
                // SHA-256 검증 (비동기, 모달 열기 전 완료)
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
        unlisten = fn;
      });
    return () => {
      unlisten?.();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    // Skip when input/textarea is focused
    if (!(e.target instanceof Element)) return;
    const tag = e.target.tagName;
    const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

    switch (e.key.toLowerCase()) {
      case "d":
        if (isInput) return;
        e.preventDefault();
        // Auto-navigate to design.submit sub-step when shortcut is pressed from elsewhere
        if (useAppStore.getState().currentSubStep !== "design.submit") {
          useAppStore.getState().setSubStep("design.submit");
        }
        tryRunDesign();
        break;
      case "o":
        e.preventDefault();
        handleOpenSequence();
        break;
      case "enter":
        if (isInput) return;
        e.preventDefault();
        // Auto-navigate to design.submit sub-step (Phase G: Run Design moved to submit step)
        if (useAppStore.getState().currentSubStep !== "design.submit") {
          useAppStore.getState().setSubStep("design.submit");
        }
        tryRunDesign();
        break;
      case "r":
        // Cmd/Ctrl+Shift+R: Reset All (isInput 포함 — 폼 입력 도중에도 동작해야 함)
        if (!e.shiftKey) return;
        e.preventDefault();
        useAppStore.getState().resetAll();
        break;
    }
  }, [tryRunDesign]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <AppShell
      tool="kuro"
      titlebar={<MenuBar />}
      subnav={<MajorSubnav majors={MAJORS} />}
      sidebar={
        /* Phase 4: WorkflowRail replaces SubStepNav in sidebar slot.
           SubStepNav is preserved below for fallback via MajorSubnav. */
        <KuroWorkflowRail />
      }
      main={
        <div
          id="major-step-main"
          className="flex flex-col flex-1 min-h-0 min-w-0 overflow-hidden"
          role="tabpanel"
          style={{ zoom }}
          aria-label={t(`phaseC.majors.${currentMajor}`, currentMajor)}
        >
          <div className="flex-shrink-0 border-b border-border">
            <SequenceViewer />
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <MajorStepView />
          </div>
          {/* Phase 4: DrawerStrip 92px bottom slot (screen-specific content) */}
          <KuroDrawerStrip />
        </div>
      }
      inspector={<KuroInspector />}
      inspectorOpen
      statusbar={
        <StatusBar
          sidecarStatus={sidecarStatus}
          onRetry={retrySidecar}
          statusErrorKind={statusErrorKind}
        />
      }
      isDragOver={isDragOver}
    >
      <WhatsNewDialog />
      <NetworkConsentDialog />

      {/* §1 Recovery: Dead-lock 감지 모달 */}
      <Dialog open={deadlockOpen} onOpenChange={setDeadlockOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("appLayout.deadlockTitle")}</DialogTitle>
            <DialogDescription>
              {t("appLayout.deadlockDesc")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setDeadlockOpen(false)}>
              {t("appLayout.deadlockWait")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-error border-error/40 hover:bg-error/8"
              onClick={() => {
                useAppStore.getState().cancelDesign();
                setDeadlockOpen(false);
              }}
            >
              {t("appLayout.deadlockReset")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
        onStatusMessage={(msg) => useAppStore.setState({ statusMessage: msg })}
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

      <Suspense fallback={null}>
        {showReport && <LazyDesignReport />}
        {showBenchmark && <LazyBenchmarkDialog />}
      </Suspense>

      {/* §5 Output Persistence: 덮어쓰기 confirm */}
      <OverwriteConfirmDialog />
    </AppShell>
  );
}
