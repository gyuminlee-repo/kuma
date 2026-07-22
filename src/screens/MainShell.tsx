import { lazy, Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { killSidecar, rpc, type SidecarKind } from "@/lib/ipc";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { GlobalAppBar, type AppTab } from "@/components/layout/GlobalAppBar";
import { useKumaProject } from "@/state/projectContext";
import { flushAutosave, onAutosaveEvent, type AutosaveTarget, type AutosaveEvent } from "@/lib/autosave";
import { useKuroAutosave } from "@/hooks/useKuroAutosave";
import { useAutosaveHydration, type HydrationStatusMessage } from "@/hooks/useAutosaveHydration";
import { Spinner } from "@/components/ui/Spinner";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { getActivityStore } from "@/store/mame/activitySlice";
import type { BusyReason } from "@/components/dialogs/CloseConfirmDialog";
import { registerShutdownHook, runShutdownHooks } from "@/lib/shutdownHook";
import { toast } from "sonner";
import { ProjectTourCoordinator } from "@/components/dialogs/ProjectTourCoordinator";

const LazySettingsDialog = lazy(async () =>
  import("@/components/layout/SettingsDialog").then((m) => ({ default: m.SettingsDialog })),
);
const LazyKuroTab = lazy(async () =>
  import("./KuroTab").then((m) => ({ default: m.KuroTab })),
);
const LazyMameTab = lazy(async () =>
  import("./MameTab").then((m) => ({ default: m.MameTab })),
);
const LazyCloseConfirmDialog = lazy(async () =>
  import("@/components/dialogs/CloseConfirmDialog").then((m) => ({ default: m.CloseConfirmDialog })),
);
const LazyJobQueuePanel = lazy(async () =>
  import("@/components/widgets/JobQueuePanel").then((m) => ({ default: m.JobQueuePanel })),
);
const LazyLogPanel = lazy(async () =>
  import("@/components/widgets/LogPanel").then((m) => ({ default: m.LogPanel })),
);

function ShellPaneFallback() {
  return (
    <div className="flex h-full items-center justify-center">
      <Spinner size="sm" />
    </div>
  );
}

// ─── 상대 시간 포맷 헬퍼 ──────────────────────────────────────────────────

type TFunc = (key: string, opts?: Record<string, string | number>) => string;

function formatRelativeTime(isoString: string, t: TFunc): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return t("mainShell.relativeTime.justNow");
  if (diffMin < 60) return t("mainShell.relativeTime.minutesAgo", { n: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return t("mainShell.relativeTime.hoursAgo", { n: diffHr });
  return t("mainShell.relativeTime.daysAgo", { n: Math.floor(diffHr / 24) });
}

// ─── autosave intro localStorage 키 ──────────────────────────────────────

const AUTOSAVE_INTRO_KEY = "kuma:autosave-intro-shown";

// ─── autosave 상태 타입 (인디케이터 전용) ────────────────────────────────

type AutosaveIndicatorState = "idle" | "saving" | "saved" | "error";

const AUTOSAVE_DOT: Record<AutosaveIndicatorState, string> = {
  idle: "bg-success",
  saving: "bg-info",
  saved: "bg-success",
  error: "bg-error",
};


function hasTauriBridge(): boolean {
  return typeof (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== "undefined";
}

async function runWithTimeout(
  label: string,
  task: () => Promise<void>,
  timeoutMs: number,
): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    await Promise.race([
      task(),
      new Promise<void>((resolve) => {
        timer = setTimeout(() => {
          console.warn(`[MainShell] ${label} timed out during close; continuing shutdown`);
          resolve();
        }, timeoutMs);
      }),
    ]);
  } catch (err) {
    console.warn(`[MainShell] ${label} failed during close; continuing shutdown`, err);
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

// ─── 컴포넌트 ─────────────────────────────────────────────────────────────

export function MainShell() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const projectName = project
    ? `${project.name}${project.scratch ? ` (${t("mainShell.scratch")})` : ""}`
    : t("mainShell.workspace");

  // ── 활성 탭 (controlled). KURO is the default (first) tab.
  const [activeTab, setActiveTab] = useState<AppTab>("kuro");
  // ── Settings 다이얼로그 (GlobalAppBar 에서 lift)
  const [settingsOpen, setSettingsOpen] = useState(false);

  // ── 상태바 좌측 메시지 (4초 자동 소멸)
  const [statusMessage, setStatusMessage] = useState("");
  const msgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logPanelVisible = useAppStore((s) => s.logPanelVisible);
  const setLogPanelVisible = useAppStore((s) => s.setLogPanelVisible);
  const jobsPanelVisible = useAppStore((s) => s.jobsPanelVisible);
  const setJobsPanelVisible = useAppStore((s) => s.setJobsPanelVisible);

  const showStatusMessage = useCallback((msg: string) => {
    if (msgTimerRef.current !== null) clearTimeout(msgTimerRef.current);
    setStatusMessage(msg);
    msgTimerRef.current = setTimeout(() => setStatusMessage(""), 4000);
  }, []);

  // §22 Graceful Shutdown: 기본 훅 등록 (pending toasts dismiss)
  useEffect(() => {
    return registerShutdownHook(() => {
      toast.dismiss();
    });
  }, []);

  // ── 두 번째 인스턴스 시도 알림
  useEffect(() => {
    if (!hasTauriBridge()) return;
    const unlisten = listen("second-instance-attempted", () => {
      showStatusMessage(t("mainShell.alreadyRunning"));
    });
    return () => {
      void unlisten.then((fn) => fn());
    };
  }, [showStatusMessage]);

  // ── autosave 인디케이터 상태
  const [autosaveState, setAutosaveState] = useState<AutosaveIndicatorState>("idle");
  const [autosaveLabel, setAutosaveLabel] = useState(() => t("mainShell.autosaveOn"));

  // ── 마지막 saved 시각 (상대 시간 갱신용)
  const lastSavedAtRef = useRef<string | null>(null);
  // ── 연속 error 카운터
  const errorStreakRef = useRef(0);

  // ── hydration 메시지 처리
  const handleHydrationMessage = useCallback((msg: HydrationStatusMessage) => {
    if (msg.variant === "restored" && msg.savedAt) {
      lastSavedAtRef.current = msg.savedAt;
      setAutosaveState("saved");
      setAutosaveLabel(t("mainShell.autosaveRestoredAgo", { time: formatRelativeTime(msg.savedAt, t) }));
    } else if (msg.variant === "restored" && msg.kind === "mame") {
      // auto-detect 결과: savedAt 없이 오는 복원 메시지 (e.g. "Auto-detected: run folder, custom barcodes")
      showStatusMessage(msg.message);
    } else if (msg.variant === "corrupted" || msg.variant === "schema_too_new") {
      showStatusMessage(msg.message);
    }
  }, [showStatusMessage, t]);

  // Phase 2: Kuro 자동 저장 구독 등록
  useKuroAutosave();
  // Phase 4: 프로젝트 진입 시 자동 저장 복원
  useAutosaveHydration(handleHydrationMessage);

  // ── autosave 이벤트 옵저버 등록
  useEffect(() => {
    const unsub = onAutosaveEvent((ev: AutosaveEvent) => {
      if (ev.type === "saving") {
        errorStreakRef.current = 0;
        setAutosaveState("saving");
        setAutosaveLabel(t("mainShell.autosaveSaving"));
      } else if (ev.type === "saved") {
        errorStreakRef.current = 0;
        lastSavedAtRef.current = ev.savedAt;
        setAutosaveState("saved");
        setAutosaveLabel(t("mainShell.autosaveSavedJustNow"));
      } else if (ev.type === "error") {
        errorStreakRef.current += 1;
        setAutosaveState("error");
        setAutosaveLabel(t("mainShell.autosaveFailed"));
        if (errorStreakRef.current >= 3) {
          showStatusMessage(t("mainShell.autosaveFailedStreak"));
        }
      }
    });
    return unsub;
  }, [showStatusMessage, t]);

  // ── 1분 단위 상대 시간 갱신 (saved 상태 전용)
  useEffect(() => {
    const id = setInterval(() => {
      if (lastSavedAtRef.current !== null && autosaveState === "saved") {
        setAutosaveLabel(t("mainShell.autosaveSavedAgo", { time: formatRelativeTime(lastSavedAtRef.current, t) }));
      }
    }, 60_000);
    return () => clearInterval(id);
  }, [autosaveState, t]);

  // ── 첫 자동 저장 인트로 (글로벌 1회, scratch 아닌 프로젝트에서만)
  useEffect(() => {
    if (!project || project.scratch) return;
    const shown = localStorage.getItem(AUTOSAVE_INTRO_KEY);
    if (shown) return;
    localStorage.setItem(AUTOSAVE_INTRO_KEY, "1");
    showStatusMessage(t("mainShell.autosaveIsOn"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.path, project?.scratch]);

  const isAutosaveActive = project !== null && project !== undefined && !project.scratch;

  // ── §19 메모리 경고 상태
  const memoryWarning = useAppStore((s) => s.memoryWarning);
  const setMemoryWarning = useAppStore((s) => s.setMemoryWarning);

  // ── close confirm 다이얼로그 상태
  const [closeDialogOpen, setCloseDialogOpen] = useState(false);
  const [closeBusyReason, setCloseBusyReason] = useState<BusyReason | null>(null);
  const [closeDialogIsBusy, setCloseDialogIsBusy] = useState(false);
  // 다이얼로그 "강제 종료" 경로: 플래그 세팅 후 destroy
  const forceCloseRef = useRef(false);
  const closeInProgressRef = useRef(false);
  const allowNativeCloseRef = useRef(false);

  const performWindowClose = useCallback(async (target: AutosaveTarget) => {
    if (closeInProgressRef.current) return;
    closeInProgressRef.current = true;

    try {
      await runWithTimeout("autosave flush", () => flushAutosave(target), 2_500);
      await runWithTimeout("shutdown hooks", runShutdownHooks, 2_500);
      await runWithTimeout(
        "sidecar shutdown",
        async () => {
          await Promise.allSettled([
            killSidecar("kuro"),
            killSidecar("mame"),
          ]);
        },
        1_500,
      );
    } finally {
      allowNativeCloseRef.current = true;
      try {
        await getCurrentWindow().destroy();
      } catch (err) {
        console.warn("[MainShell] window destroy failed during close; falling back to close", err);
        await getCurrentWindow().close();
      }
    }
  }, []);

  // ── isBusy 실시간 추적 (다이얼로그 Wait → 자동 close 용)
  useEffect(() => {
    if (!closeDialogOpen) return;
    const id = setInterval(() => {
      const { isDesigning, isExporting: kuroExporting } = useAppStore.getState();
      const { isAnalyzing, isExporting: mameExporting } = useMameAppStore.getState();
      const activityExporting = getActivityStore()?.getState().isExporting ?? false;
      setCloseDialogIsBusy(isDesigning || isAnalyzing || kuroExporting || mameExporting || activityExporting);
    }, 200);
    return () => clearInterval(id);
  }, [closeDialogOpen]);

  // ── 윈도우 close 직전 flush (kuro + mame 양쪽)
  useEffect(() => {
    const target: AutosaveTarget = {
      projectPath: project?.path ?? null,
      scratch: project?.scratch ?? true,
      // 프로젝트가 없어도 KURO 상태는 앱 데이터 디렉토리에 남긴다.
      scratchFallback: true,
    };

    let unlisten: (() => void) | undefined;
    void getCurrentWindow()
      .onCloseRequested(async (ev) => {
        if (allowNativeCloseRef.current) {
          return;
        }
        ev.preventDefault();

        // 강제 종료 플래그: 다이얼로그 "강제 종료" 버튼에서 왔으면 바로 destroy
        if (forceCloseRef.current) {
          forceCloseRef.current = false;
          await performWindowClose(target);
          return;
        }

        // 진행 중 작업 여부를 store에서 직접 읽음 (deps 재등록 방지)
        const { isDesigning, isExporting: kuroExporting } = useAppStore.getState();
        const { isAnalyzing, isExporting: mameExporting } = useMameAppStore.getState();
        const activityExporting = getActivityStore()?.getState().isExporting ?? false;

        const isExportingAny = kuroExporting || mameExporting || activityExporting;
        const isBusy = isDesigning || isAnalyzing || isExportingAny;

        if (isBusy) {
          // 분기별 reason 결정 (우선순위: export > analyzing > designing)
          const reason: BusyReason = isExportingAny
            ? "exporting"
            : isAnalyzing
              ? "analyzing"
              : "designing";

          setCloseBusyReason(reason);
          setCloseDialogIsBusy(true);
          setCloseDialogOpen(true);
          return;
        }

        await performWindowClose(target);
      })
      .then((fn) => {
        unlisten = fn;
      });

    return () => {
      unlisten?.();
    };
  }, [performWindowClose, project?.path, project?.scratch]);

  // ── 탭 전환 직전 flush
  // prevTab is read from the controlled state; flush whichever kuro/mame tab is
  // being left. Then lazily spawn the destination sidecar.
  async function handleTabChange(nextKind: string): Promise<void> {
    const prevTab = activeTab;
    const target: AutosaveTarget = {
      projectPath: project?.path ?? null,
      scratch: project?.scratch ?? true,
      // 프로젝트가 없어도 KURO 상태는 앱 데이터 디렉토리에 남긴다.
      scratchFallback: true,
    };

    // Flush the tab being left when it is a kuro/mame autosave target.
    if (prevTab === "kuro" || prevTab === "mame") {
      await flushAutosave(target, prevTab);
    }

    // Lazily start the destination sidecar for autosave-backed tabs.
    if (nextKind === "kuro" || nextKind === "mame") {
      void rpc(nextKind as SidecarKind, "ping", {}).catch(() => {
        // Ignore lazy sidecar startup failures in the shell.
      });
    }
  }

  // ── close confirm 핸들러
  const handleCloseWait = useCallback(() => {
    // 대기 선택: 다이얼로그 유지. isBusy가 false가 되면 useEffect가 자동 close.
  }, []);

  const handleForceClose = useCallback(() => {
    setCloseDialogOpen(false);
    forceCloseRef.current = true;
    void getCurrentWindow().close();
  }, []);

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* 4초 소멸 상태바 메시지 (autosave 인트로 / 연속 실패 토스트 등) */}
      {statusMessage && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="px-3 py-1 text-caption text-muted-foreground bg-muted border-b border-border shrink-0"
        >
          {statusMessage}
        </div>
      )}

      {/* §19 메모리 경고 배너 (warn 레벨) */}
      {memoryWarning && memoryWarning.level === "warn" && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="flex items-center justify-between px-3 py-1 text-caption bg-warning/20 text-warning-foreground border-b border-warning/40 shrink-0"
        >
          <span>
            {t("mainShell.memoryWarning", {
              ratio: Math.round(memoryWarning.ratio * 100),
              rss: memoryWarning.rss_mb.toFixed(0),
            })}
          </span>
          <button
            type="button"
            aria-label={t("mainShell.memoryWarningDismissAriaLabel")}
            className="ml-2 text-warning-foreground opacity-70 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setMemoryWarning(null)}
          >
            ✕
          </button>
        </div>
      )}

      {/* §19 메모리 초과 모달 (block 레벨) */}
      {memoryWarning && memoryWarning.level === "block" && (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="mem-block-title"
          aria-describedby="mem-block-desc"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
        >
          <div className="mx-4 max-w-sm rounded-xl border border-destructive bg-background p-6 shadow-xl">
            <h2 id="mem-block-title" className="mb-2 text-base font-semibold text-destructive">
              {t("mainShell.memoryBlockTitle")}
            </h2>
            <p id="mem-block-desc" className="mb-4 text-sm text-muted-foreground">
              {t("mainShell.memoryBlockDesc", {
                ratio: Math.round(memoryWarning.ratio * 100),
                rss: memoryWarning.rss_mb.toFixed(0),
              })}
            </p>
            <button
              type="button"
              className="w-full rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setMemoryWarning(null)}
            >
              {t("mainShell.memoryBlockConfirm")}
            </button>
          </div>
        </div>
      )}

      <GlobalAppBar
        activeTab={activeTab}
        onTabChange={(v) => {
          setActiveTab(v);
          void handleTabChange(v);
        }}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <Suspense fallback={null}>
        <LazySettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} scope={activeTab} />
      </Suspense>

      <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v as AppTab); void handleTabChange(v); }} className="flex min-h-0 flex-1 flex-col">
        <header
          data-tour="project-status"
          className="h-header flex shrink-0 items-center border-b bg-background px-4"
        >
          <div className="flex w-full min-w-0 items-center gap-4">
            <div className="min-w-0 flex-1 text-caption text-muted-foreground">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate font-medium text-foreground">{projectName}</span>
                {project?.stage ? (
                  <span className="shrink-0 rounded-full border border-border bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
                    {project.stage}
                  </span>
                ) : null}
              </div>
            </div>

            {/* autosave 인디케이터 (scratch 아닌 프로젝트에서만 표시) */}
            {isAutosaveActive && (
              <span
                className="flex shrink-0 items-center gap-1.5 text-caption text-muted-foreground"
                aria-label={t("mainShell.autosaveAriaLabel", { label: autosaveLabel })}
              >
                <span
                  className={`h-2 w-2 rounded-full shrink-0 ${AUTOSAVE_DOT[autosaveState]}`}
                  aria-hidden="true"
                />
                <span className="whitespace-nowrap">{autosaveLabel}</span>
                {autosaveState === "saving" && <Spinner size="sm" />}
                {autosaveState === "error" && (
                  <button
                    type="button"
                    className="text-error underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast"
                    onClick={() => {
                      errorStreakRef.current = 0;
                      setAutosaveState("idle");
                      setAutosaveLabel(t("mainShell.autosaveOn"));
                    }}
                    aria-label={t("mainShell.autosaveRetryAriaLabel")}
                  >
                    {t("mainShell.autosaveRetry")}
                  </button>
                )}
              </span>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-hidden">
          <TabsContent value="kuro" className="mt-0 h-full overflow-hidden">
            <Suspense fallback={<ShellPaneFallback />}>
              <LazyKuroTab />
            </Suspense>
          </TabsContent>
          <TabsContent value="mame" className="mt-0 h-full overflow-hidden">
            <Suspense fallback={<ShellPaneFallback />}>
              <LazyMameTab />
            </Suspense>
          </TabsContent>
        </div>
      </Tabs>

      {project && !project.scratch && (
        <ProjectTourCoordinator
          key={project.project_id ?? project.path}
          project={project}
          activeTab={activeTab}
          onTabChange={(tab) => {
            setActiveTab(tab);
            void handleTabChange(tab);
          }}
        />
      )}

      {/* §13 Background Job Queue floating panel */}
      <Suspense fallback={null}>
        {jobsPanelVisible && (
          <LazyJobQueuePanel onClose={() => setJobsPanelVisible(false)} />
        )}

        {/* §2 Observability: sidecar log panel */}
        {logPanelVisible && (
          <LazyLogPanel onClose={() => setLogPanelVisible(false)} />
        )}
      </Suspense>

      {/* §22 Graceful Shutdown: busy 상태 close 확인 */}
      <Suspense fallback={null}>
        <LazyCloseConfirmDialog
          open={closeDialogOpen}
          reason={closeBusyReason}
          isBusy={closeDialogIsBusy}
          onWait={handleCloseWait}
          onForceClose={handleForceClose}
        />
      </Suspense>
    </div>
  );
}
