import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useKumaProject } from "@/state/projectContext";
import { selectCanRun } from "@/store/mame/selectors";
import { useMameSidecar } from "@/hooks/mame/useMameSidecar";
import { initActivityStore } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { tryHandleManifestDrop, tryHandleTwoManifestsDrop, verifyInputs, type InputVerifyResult } from "@/lib/reRun";
import { type RunManifest } from "@/lib/runManifest";
import { ReRunManifestDialog } from "@/components/dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "@/components/dialogs/ManifestDiffDialog";
import { ClearConfirmDialog } from "../dialogs/ClearConfirmDialog";
import { ExportDialog } from "../dialogs/ExportDialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { startDeadlockWatch } from "@/lib/deadlockDetector";
import { getLastProgressAt } from "@/lib/ipc-mame";
import { PreflightDialog } from "@/components/dialogs/PreflightDialog";
import { OverwriteConfirmDialog } from "@/components/dialogs/OverwriteConfirmDialog";
import { runPreflightCheck } from "@/lib/preflight";
import type { PreflightResult } from "@/lib/preflight";
import { MenuBar } from "./MenuBar";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { PlateView } from "../widgets/PlateView";
import { SummaryRow } from "../widgets/SummaryRow";
import { VerdictTable } from "../widgets/VerdictTable";
import { RunHealthPanel } from "../widgets/RunHealthPanel";
import { DataPanel } from "@/components/ui/Panel";

// Activity store는 RoundStore를 주입받아 초기화 (lazy singleton).
// MameAppLayout 모듈 로드 시 단 한 번만 실행.
initActivityStore(useRoundStore);

const SEQUENCE_EXTENSIONS = new Set([".fa", ".fasta", ".fna"]);
const XLSX_EXTENSIONS = new Set([".xlsx"]);

export function MameAppLayout() {
  const project = useKumaProject();
  const { status, retry } = useMameSidecar();
  const clearResults = useMameAppStore((s) => s.clearResults);
  const runHealth = useMameAppStore((s) => s.runHealth);
  const verdictsLength = useMameAppStore((s) => s.verdicts.length);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
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
   * Sidebar Run 버튼과 키보드 단축키 모두 이 콜백을 사용.
   */
  const tryRunAnalysis = useCallback(() => {
    const s = useMameAppStore.getState();
    if (!selectCanRun(s)) return;
    void runPreflightCheck({ sidecarStatus: status, requiresNetwork: false }).then(
      (pfResult) => {
        const actualRun = () => void s.runAnalysis();
        if (!pfResult.ok || pfResult.warnings.length > 0) {
          setPreflightResult({ result: pfResult, pendingAction: actualRun });
        } else {
          actualRun();
        }
      },
    );
  }, [status]);

  // §1 Dead-lock 감지: analysis 진행 중 30초 progress 정적 시 모달 표시
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
                setReRunStatusMsg(`Manifest 로드 실패: ${twoResult.error}`);
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
                setReRunStatusMsg(`Manifest 로드 실패: ${result.error}`);
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
        case "o":
          e.preventDefault();
          void s.loadWorkspace(project);
          break;
        case "s":
          e.preventDefault();
          void s.saveWorkspace(project);
          break;
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

  return (
    <div
      className={`flex h-full flex-col bg-background ${isDragOver ? "ring-2 ring-inset ring-ring" : ""}`}
    >
      <MenuBar onClearRequest={() => setClearConfirmOpen(true)} />

      <div className="flex flex-1 gap-3 overflow-hidden p-3">
        <Sidebar
          onClearRequest={() => setClearConfirmOpen(true)}
          onRunRequest={tryRunAnalysis}
        />

        <main
          className="grid min-h-0 flex-1 min-w-0 grid-rows-[auto_minmax(0,1fr)_320px_auto] gap-3 overflow-hidden"
          role="main"
          aria-label="Analysis workspace"
        >
          <SummaryRow />
          <DataPanel title="Verdict table" className="min-h-0">
            <VerdictTable />
          </DataPanel>
          <DataPanel title="Plate plan">
            <PlateView />
          </DataPanel>
          {verdictsLength > 0 && runHealth !== null && (
            <DataPanel title="Run health">
              <RunHealthPanel health={runHealth} />
            </DataPanel>
          )}
        </main>
      </div>

      <StatusBar sidecarStatus={status} onRetry={retry} />

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
                void useMameAppStore.getState().cancelAnalysis();
                setDeadlockOpen(false);
              }}
            >
              Reset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ExportDialog />
      <ClearConfirmDialog
        open={clearConfirmOpen}
        onOpenChange={setClearConfirmOpen}
        onConfirm={clearResults}
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
    </div>
  );
}

