import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { WifiOff } from "lucide-react";
import { classifyError } from "@/lib/errorClassifier";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useAppStore } from "../../store/appStore";
import { useSidecar } from "../../hooks/useSidecar";
import { useKumaProject } from "../../state/projectContext";
import { useFlushKuroBeforeDesign } from "../../hooks/useKuroAutosave";
import { tryHandleManifestDrop, tryHandleTwoManifestsDrop, verifyInputs, type InputVerifyResult } from "@/lib/reRun";
import { type RunManifest } from "@/lib/runManifest";
import { ReRunManifestDialog } from "../dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "../dialogs/ManifestDiffDialog";

const IS_MAC = typeof navigator !== "undefined" && navigator.userAgent.includes("Mac");
const RUN_HINT = IS_MAC ? "⌘↵" : "Ctrl+↵";
import { InputPanel } from "../panels/InputPanel";
import { ParameterPanel } from "../panels/ParameterPanel";
import { ResultTable } from "../widgets/ResultTable";
import { SequenceViewer } from "../widgets/SequenceViewer";
import { PlateMap } from "../widgets/PlateMap";
import { Button } from "../ui/button";
import { DataPanel } from "../ui/Panel";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { MenuBar } from "./MenuBar";
import { StatusBar } from "./StatusBar";
import { NetworkConsentDialog } from "../dialogs/NetworkConsentDialog";
import { InputSizeWarningDialog } from "../dialogs/InputSizeWarningDialog";
import { PreflightDialog } from "../dialogs/PreflightDialog";
import { OverwriteConfirmDialog } from "../dialogs/OverwriteConfirmDialog";
import { checkKuroInputSize } from "@/lib/inputThresholds";
import type { InputSizeLevel } from "@/lib/inputThresholds";
import { runPreflightCheck } from "@/lib/preflight";
import type { PreflightResult } from "@/lib/preflight";
import {
  handleExportExcel,
  handleSaveWorkspace,
  handleOpenSequence,
} from "./export-handlers";
import { startDeadlockWatch } from "@/lib/deadlockDetector";
import { getLastProgressAt } from "@/lib/ipc-kuro";

const SEQUENCE_EXTENSIONS = new Set([".gb", ".gbk", ".gbff", ".dna", ".fa", ".fasta"]);
const CSV_EXTENSIONS = new Set([".csv"]);
const LazyDesignReport = lazy(async () => import("../dialogs/DesignReport").then((m) => ({ default: m.DesignReport })));
const LazyBenchmarkDialog = lazy(async () => import("../dialogs/BenchmarkDialog").then((m) => ({ default: m.BenchmarkDialog })));

export function AppLayout() {
  const project = useKumaProject();
  const { status: sidecarStatus, retry: retrySidecar } = useSidecar();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);

  // §4 네트워크 에러 분리 — statusMessage를 분류해 WifiOff 아이콘 표시
  const statusErrorKind = useMemo(() => {
    if (!statusMessage) return null;
    // 에러 키워드가 포함된 메시지에만 적용 (모든 status에 아이콘 붙이면 노이즈)
    if (!/fail|error|timeout|refused/i.test(statusMessage)) return null;
    return classifyError(statusMessage).kind;
  }, [statusMessage]);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const loadPolymerases = useAppStore((s) => s.loadPolymerases);
  const showReport = useAppStore((s) => s.showReport);
  const showBenchmark = useAppStore((s) => s.showBenchmark);
  const loadNetworkConsentSettings = useAppStore((s) => s.loadNetworkConsentSettings);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [missingFields, setMissingFields] = useState<string[] | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  // §1 Dead-lock 감지 모달 상태
  const [deadlockOpen, setDeadlockOpen] = useState(false);

  // §19 Performance Guardrails: 입력 크기 사전 경고 상태
  const [kuroSizeWarning, setKuroSizeWarning] = useState<{
    level: InputSizeLevel;
    message: string;
    pendingAction: () => void;
  } | null>(null);

  // §19 Performance Guardrails: pre-flight check 결과 상태
  const [preflightResult, setPreflightResult] = useState<{
    result: PreflightResult;
    pendingAction: () => void;
  } | null>(null);

  // §12 Reproducibility: manifest re-run 모달 상태
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);
  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);
  const reRunVerifyRef = useRef<InputVerifyResult | null>(null);

  // §12 Reproducibility: manifest diff 모달 상태
  const [diffManifestA, setDiffManifestA] = useState<RunManifest | null>(null);
  const [diffManifestB, setDiffManifestB] = useState<RunManifest | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  // C-1: Run Design 직전 flush (입력 보존 — 실패 시에도 복원 가능)
  const flushBeforeDesign = useFlushKuroBeforeDesign();

  /**
   * Collect missing required inputs for design.
   * Returns an empty array when ready to run.
   */
  const collectMissingFields = useCallback((): string[] => {
    const s = useAppStore.getState();
    const missing: string[] = [];
    if (!s.seqInfo) missing.push("Sequence file (Browse a .gb / .fasta / .dna file)");
    if (!s.mutationText.trim()) missing.push("Mutations (enter at least one mutation in the Mutation panel)");
    if (s.seqInfo && s.seqInfo.genes.length > 1 && !s.selectedGene) {
      missing.push("Target gene (select one in the Sequence panel)");
    }
    return missing;
  }, []);

  /**
   * Click handler: validate first, then run. If anything is missing, show a popup.
   * §19: After validation, check input size; show warning dialog if threshold exceeded.
   */
  const tryRunDesign = useCallback(() => {
    if (useAppStore.getState().isDesigning) return;
    const missing = collectMissingFields();
    if (missing.length > 0) {
      setMissingFields(missing);
      return;
    }

    // §19 입력 크기 검사
    const mutationText = useAppStore.getState().mutationText;
    const rowCount = mutationText
      .trim()
      .split("\n")
      .filter((l) => l.trim() && !l.trim().startsWith("#")).length;
    const sizeCheck = checkKuroInputSize({ rowCount });

    // §19 pre-flight: sidecar alive + disk space (best-effort) — kuro design은 외부 호출 없음
    const runWithPreflight = () => {
      void runPreflightCheck({ sidecarStatus, requiresNetwork: false }).then(
        (pfResult) => {
          const actualRun = () => {
            void flushBeforeDesign().then(() =>
              useAppStore.getState().designPrimers(),
            );
          };
          if (!pfResult.ok || pfResult.warnings.length > 0) {
            setPreflightResult({ result: pfResult, pendingAction: actualRun });
          } else {
            actualRun();
          }
        },
      );
    };

    if (sizeCheck.level !== "ok") {
      setKuroSizeWarning({
        level: sizeCheck.level,
        message: sizeCheck.message,
        pendingAction: runWithPreflight,
      });
      return;
    }

    runWithPreflight();
  }, [collectMissingFields, flushBeforeDesign]);

  const selectedGeneInfo = seqInfo?.genes.find((gene) => String(gene.cds_start) === selectedGene);
  const plateEstimate = totalCount > 0 ? Math.ceil(totalCount / 96) : null;

  useEffect(() => {
    loadNetworkConsentSettings();
  }, [loadNetworkConsentSettings]);

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
                useAppStore.setState({ statusMessage: `Manifest 로드 실패: ${twoResult.error}` });
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
                useAppStore.setState({ statusMessage: `Manifest 로드 실패: ${result.error}` });
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
      case "s":
        e.preventDefault();
        void handleSaveWorkspace(project);
        break;
      case "e":
        if (isInput) return;
        e.preventDefault();
        if (useAppStore.getState().designResults.length > 0) handleExportExcel(project?.project_id);
        break;
      case "d":
        if (isInput) return;
        e.preventDefault();
        tryRunDesign();
        break;
      case "o":
        e.preventDefault();
        handleOpenSequence();
        break;
      case "enter":
        if (isInput) return;
        e.preventDefault();
        tryRunDesign();
        break;
      case "r":
        // Cmd/Ctrl+Shift+R: Reset All (isInput 포함 — 폼 입력 도중에도 동작해야 함)
        if (!e.shiftKey) return;
        e.preventDefault();
        if (hasDesignResults) {
          setClearConfirmOpen(true);
        } else {
          useAppStore.getState().resetAll();
        }
        break;
    }
  }, [flushBeforeDesign, hasDesignResults, project, tryRunDesign]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className={`flex h-screen flex-col bg-background ${isDragOver ? "ring-2 ring-inset ring-ring" : ""}`}>
      <NetworkConsentDialog />
      <MenuBar />

      <div className="flex flex-1 overflow-hidden px-3 pb-3 pt-2">
        <PanelGroup
          direction="horizontal"
          autoSaveId="kuma-main-h"
          className="flex-1 min-w-0 overflow-hidden"
        >
          <Panel
            defaultSize={22}
            minSize={16}
            maxSize={40}
            className="flex min-h-0 flex-col"
          >
          <aside
            data-testid="sidebar"
            className="flex h-full min-h-0 flex-col overflow-hidden rounded-container border border-border bg-card"
          >
            <div className="min-h-0 flex-1 overflow-y-auto p-3 space-y-3">
              <InputPanel />
              <ParameterPanel />
            </div>

            <footer className="border-t border-border bg-muted/40 px-3 py-3 space-y-2">
              <div
                aria-live="polite"
                aria-atomic="true"
                role={statusErrorKind === "network" ? "alert" : undefined}
                className="px-1"
              >
                <span className="text-caption text-muted-foreground">Status</span>
                <div className="flex items-center gap-1.5 min-w-0">
                  {statusErrorKind === "network" && (
                    <WifiOff
                      size={13}
                      className="flex-shrink-0 text-amber-500 dark:text-amber-400"
                      aria-hidden="true"
                    />
                  )}
                  <p
                    className={
                      statusErrorKind === "network"
                        ? "truncate text-body font-medium text-amber-500 dark:text-amber-400"
                        : "truncate text-body font-medium text-foreground"
                    }
                  >
                    {statusMessage}
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  className="h-control-primary flex-1 min-w-0 rounded-control text-body font-semibold"
                  onClick={tryRunDesign}
                  disabled={isDesigning}
                >
                  {isDesigning ? "Designing..." : "Run Design"}
                  {!isDesigning && (
                    <kbd className="ml-2 text-caption text-muted-foreground font-normal opacity-70">{RUN_HINT}</kbd>
                  )}
                </Button>
                {isDesigning && (
                  <Button
                    variant="outline"
                    className="h-control-primary rounded-control px-3 text-error border-error/40 hover:bg-error/8"
                    onClick={() => useAppStore.getState().cancelDesign()}
                  >
                    Cancel
                  </Button>
                )}
              </div>
              <Button
                variant="outline"
                className="h-control w-full rounded-control"
                onClick={() => {
                  if (hasDesignResults) {
                    setClearConfirmOpen(true);
                  } else {
                    useAppStore.getState().resetAll();
                  }
                }}
                disabled={isDesigning}
              >
                Clear All
              </Button>
            </footer>
          </aside>
          </Panel>

          <PanelResizeHandle className="w-1.5 mx-1 rounded-full bg-transparent hover:bg-border data-[resize-handle-active]:bg-ring transition-colors" />

          <Panel className="flex min-h-0 flex-col" minSize={40}>
          <main
            data-testid="main-content"
            className="flex h-full min-h-0 flex-col overflow-hidden"
          >
            <PanelGroup direction="vertical" autoSaveId="kuma-main-v" className="flex-1 min-h-0">
              <Panel defaultSize={18} minSize={10} className="min-h-0">
                <DataPanel
                  title="Sequence context"
                  description={selectedGeneInfo ? `${selectedGeneInfo.gene} · ${selectedGeneInfo.aa_length} aa` : "Load a target gene"}
                  className="h-full overflow-hidden"
                >
                  <div className="h-full">
                    <SequenceViewer />
                  </div>
                </DataPanel>
              </Panel>

              <PanelResizeHandle className="h-1.5 my-1 rounded-full bg-transparent hover:bg-border data-[resize-handle-active]:bg-ring transition-colors" />

              <Panel defaultSize={34} minSize={15} className="min-h-0">
                <DataPanel
                  title="Design output"
                  description={hasDesignResults ? `${successCount}/${totalCount} successful` : "No results yet"}
                  className="h-full min-h-0 overflow-hidden"
                >
                  <div className="min-h-0 h-full">
                    <ResultTable />
                  </div>
                </DataPanel>
              </Panel>

              <PanelResizeHandle className="h-1.5 my-1 rounded-full bg-transparent hover:bg-border data-[resize-handle-active]:bg-ring transition-colors" />

              <Panel defaultSize={48} minSize={35} className="min-h-0">
                <DataPanel
                  title="Plate plan"
                  description={plateEstimate ? `${plateEstimate} plate${plateEstimate > 1 ? "s" : ""}` : "Awaiting design"}
                  className="h-full overflow-hidden"
                >
                  <div className="h-full min-h-[400px] overflow-auto">
                    <PlateMap />
                  </div>
                </DataPanel>
              </Panel>
            </PanelGroup>
          </main>
          </Panel>
        </PanelGroup>
      </div>

      <StatusBar sidecarStatus={sidecarStatus} onRetry={retrySidecar} />

      <Dialog open={clearConfirmOpen} onOpenChange={setClearConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Clear All</DialogTitle>
            <DialogDescription>
              All design results will be lost. Continue?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setClearConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-error border-error/40 hover:bg-error/8"
              onClick={() => {
                useAppStore.getState().resetAll();
                setClearConfirmOpen(false);
              }}
            >
              Clear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={missingFields !== null}
        onOpenChange={(open) => {
          if (!open) setMissingFields(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cannot run design yet</DialogTitle>
            <DialogDescription>
              Fill in the following before running design:
            </DialogDescription>
          </DialogHeader>
          <ul className="list-disc pl-5 text-body text-foreground space-y-1">
            {missingFields?.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          <DialogFooter>
            <Button size="sm" onClick={() => setMissingFields(null)}>
              OK
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* §1 Recovery: Dead-lock 감지 모달 */}
      <Dialog open={deadlockOpen} onOpenChange={setDeadlockOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>응답 없음</DialogTitle>
            <DialogDescription>
              30초 이상 진행 상태가 업데이트되지 않았습니다. 작업이 멈춘 것 같습니다.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setDeadlockOpen(false)}>
              계속 대기
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
              Reset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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

      {/* §19 Performance Guardrails: kuro 입력 크기 사전 경고 */}
      {kuroSizeWarning && (
        <InputSizeWarningDialog
          open={kuroSizeWarning !== null}
          level={kuroSizeWarning.level}
          message={kuroSizeWarning.message}
          onContinue={() => {
            const action = kuroSizeWarning.pendingAction;
            setKuroSizeWarning(null);
            action();
          }}
          onCancel={() => setKuroSizeWarning(null)}
        />
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
    </div>
  );
}
