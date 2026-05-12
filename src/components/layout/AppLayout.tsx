import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { classifyError } from "@/lib/errorClassifier";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { AppShell } from "../shell/AppShell";
import { useAppStore } from "../../store/appStore";
import { useSidecar } from "../../hooks/useSidecar";
import { useKumaProject } from "../../state/projectContext";
import { useFlushKuroBeforeDesign } from "../../hooks/useKuroAutosave";
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
import { KuroAppBar } from "./KuroAppBar";
import { MajorSubnav, type MajorNavItem } from "./MajorSubnav";
import { SubStepNav, type SubNavItem } from "./SubStepNav";
import { MajorStepView } from "../steps/MajorStepView";
import { StatusBar } from "./StatusBar";
import { WhatsNewDialog } from "../dialogs/WhatsNewDialog";
import { NetworkConsentDialog } from "../dialogs/NetworkConsentDialog";
import { InputSizeWarningDialog } from "../dialogs/InputSizeWarningDialog";
import { PreflightDialog } from "../dialogs/PreflightDialog";
import { OverwriteConfirmDialog } from "../dialogs/OverwriteConfirmDialog";
import { checkKuroInputSize } from "@/lib/inputThresholds";
import type { InputSizeLevel } from "@/lib/inputThresholds";
import { runPreflightCheck } from "@/lib/preflight";
import type { PreflightResult } from "@/lib/preflight";
import { handleOpenSequence } from "./export-handlers";
import { startDeadlockWatch } from "@/lib/deadlockDetector";
import { getLastProgressAt } from "@/lib/ipc-kuro";
import { MAJOR_ORDER, SUBSTEP_ORDER } from "@/store/slices/navigationSlice";
import type { MajorStepId } from "@/store/slices/navigationSlice";

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
    if (!s.seqInfo) missing.push(t("appLayout.missingSeqFile"));
    if (!s.mutationText.trim()) missing.push(t("appLayout.missingMutations"));
    if (s.seqInfo && s.seqInfo.genes.length > 1 && !s.selectedGene) {
      missing.push(t("appLayout.missingTargetGene"));
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

  // Navigation state for AppShell slot wiring
  const currentMajor = useAppStore((s) => s.currentMajor);

  // Build MAJORS and SUBSTEPS arrays from navigationSlice constants
  const MAJORS: MajorNavItem[] = MAJOR_ORDER.map((id) => ({
    id,
    labelKey: `phaseC.majors.${id}`,
  }));

  const SUBSTEPS: Record<MajorStepId, SubNavItem[]> = Object.fromEntries(
    MAJOR_ORDER.map((major) => [
      major,
      SUBSTEP_ORDER[major].map((id) => ({
        id,
        labelKey: `phaseC.subSteps.${id}`,
      })),
    ]),
  ) as Record<MajorStepId, SubNavItem[]>;

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
        // Auto-navigate to sdm.run sub-step when shortcut is pressed from elsewhere
        if (useAppStore.getState().currentSubStep !== "sdm.run") {
          useAppStore.getState().setSubStep("sdm.run");
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
        // Auto-navigate to sdm.run sub-step (spec §9: 단축키 sdm.run 자동 전환)
        if (useAppStore.getState().currentSubStep !== "sdm.run") {
          useAppStore.getState().setSubStep("sdm.run");
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
      appbar={<KuroAppBar />}
      subnav={<MajorSubnav majors={MAJORS} />}
      sidebar={
        <SubStepNav
          major={currentMajor}
          subSteps={SUBSTEPS[currentMajor]}
        />
      }
      main={
        <div
          id="major-step-main"
          className="flex flex-1 min-h-0 min-w-0 overflow-hidden"
          role="tabpanel"
          aria-label={t(`phaseC.majors.${currentMajor}`, currentMajor)}
        >
          <MajorStepView />
        </div>
      }
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

      <Dialog
        open={missingFields !== null}
        onOpenChange={(open) => {
          if (!open) setMissingFields(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("appLayout.cannotRunTitle")}</DialogTitle>
            <DialogDescription>
              {t("appLayout.cannotRunDesc")}
            </DialogDescription>
          </DialogHeader>
          <ul className="list-disc pl-5 text-body text-foreground space-y-1">
            {missingFields?.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          <DialogFooter>
            <Button size="sm" onClick={() => setMissingFields(null)}>
              {t("common.ok")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
    </AppShell>
  );
}
