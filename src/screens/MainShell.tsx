import { useEffect, useRef, useState, useCallback } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { killSidecar, rpc, type SidecarKind } from "@/lib/ipc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKumaProject } from "@/state/projectContext";
import { flushAutosave, onAutosaveEvent, type AutosaveTarget, type AutosaveEvent } from "@/lib/autosave";
import { useKuroAutosave } from "@/hooks/useKuroAutosave";
import { useAutosaveHydration, type HydrationStatusMessage } from "@/hooks/useAutosaveHydration";
import { Spinner } from "@/components/ui/Spinner";
import { KuroTab } from "./KuroTab";
import { MameTab } from "./MameTab";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { getActivityStore } from "@/store/mame/activitySlice";
import { CloseConfirmDialog, type BusyReason } from "@/components/dialogs/CloseConfirmDialog";
import { JobQueuePanel } from "@/components/widgets/JobQueuePanel";
import { LogPanel } from "@/components/widgets/LogPanel";
import { registerShutdownHook, runShutdownHooks } from "@/lib/shutdownHook";
import { toast } from "sonner";

// ─── 상대 시간 포맷 헬퍼 ──────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  return `${Math.floor(diffHr / 24)} day(s) ago`;
}

// ─── autosave intro localStorage 키 ──────────────────────────────────────

const AUTOSAVE_INTRO_KEY = "kuma:autosave-intro-shown";
const LOG_PANEL_VISIBLE_KEY = "kuma:floating-panel:log:visible";
const JOBS_PANEL_VISIBLE_KEY = "kuma:floating-panel:jobs:visible";

// ─── autosave 상태 타입 (인디케이터 전용) ────────────────────────────────

type AutosaveIndicatorState = "idle" | "saving" | "saved" | "error";

const AUTOSAVE_DOT: Record<AutosaveIndicatorState, string> = {
  idle: "bg-success",
  saving: "bg-info",
  saved: "bg-success",
  error: "bg-error",
};

function readVisiblePreference(key: string): boolean {
  if (typeof window === "undefined") return true;
  const raw = window.localStorage.getItem(key);
  return raw === null ? true : raw === "true";
}

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
  const project = useKumaProject();
  const projectName = project ? `${project.name}${project.scratch ? " (Scratch)" : ""}` : "Workspace";

  // ── 상태바 좌측 메시지 (4초 자동 소멸)
  const [statusMessage, setStatusMessage] = useState("");
  const msgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [logPanelVisible, setLogPanelVisible] = useState(() =>
    readVisiblePreference(LOG_PANEL_VISIBLE_KEY),
  );
  const [jobsPanelVisible, setJobsPanelVisible] = useState(() =>
    readVisiblePreference(JOBS_PANEL_VISIBLE_KEY),
  );

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
      showStatusMessage("이미 실행 중입니다.");
    });
    return () => {
      void unlisten.then((fn) => fn());
    };
  }, [showStatusMessage]);

  useEffect(() => {
    window.localStorage.setItem(LOG_PANEL_VISIBLE_KEY, String(logPanelVisible));
  }, [logPanelVisible]);

  useEffect(() => {
    window.localStorage.setItem(JOBS_PANEL_VISIBLE_KEY, String(jobsPanelVisible));
  }, [jobsPanelVisible]);

  // ── autosave 인디케이터 상태
  const [autosaveState, setAutosaveState] = useState<AutosaveIndicatorState>("idle");
  const [autosaveLabel, setAutosaveLabel] = useState("Autosave on");

  // ── 마지막 saved 시각 (상대 시간 갱신용)
  const lastSavedAtRef = useRef<string | null>(null);
  // ── 연속 error 카운터
  const errorStreakRef = useRef(0);

  // ── hydration 메시지 처리
  const handleHydrationMessage = useCallback((msg: HydrationStatusMessage) => {
    if (msg.variant === "restored" && msg.savedAt) {
      lastSavedAtRef.current = msg.savedAt;
      setAutosaveState("saved");
      setAutosaveLabel(`Restored from autosave (${formatRelativeTime(msg.savedAt)})`);
    } else if (msg.variant === "restored" && msg.kind === "mame") {
      // auto-detect 결과: savedAt 없이 오는 복원 메시지 (e.g. "Auto-detected: run folder, custom barcodes")
      showStatusMessage(msg.message);
    } else if (msg.variant === "corrupted" || msg.variant === "schema_too_new") {
      showStatusMessage(msg.message);
    }
  }, [showStatusMessage]);

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
        setAutosaveLabel("Saving…");
      } else if (ev.type === "saved") {
        errorStreakRef.current = 0;
        lastSavedAtRef.current = ev.savedAt;
        setAutosaveState("saved");
        setAutosaveLabel("Saved just now");
      } else if (ev.type === "error") {
        errorStreakRef.current += 1;
        setAutosaveState("error");
        setAutosaveLabel("Save failed");
        if (errorStreakRef.current >= 3) {
          showStatusMessage("Autosave failed 3 times. Check disk space or permissions.");
        }
      }
    });
    return unsub;
  }, [showStatusMessage]);

  // ── 1분 단위 상대 시간 갱신 (saved 상태 전용)
  useEffect(() => {
    const id = setInterval(() => {
      if (lastSavedAtRef.current !== null && autosaveState === "saved") {
        setAutosaveLabel(`Saved ${formatRelativeTime(lastSavedAtRef.current)}`);
      }
    }, 60_000);
    return () => clearInterval(id);
  }, [autosaveState]);

  // ── 첫 자동 저장 인트로 (글로벌 1회, scratch 아닌 프로젝트에서만)
  useEffect(() => {
    if (!project || project.scratch) return;
    const shown = localStorage.getItem(AUTOSAVE_INTRO_KEY);
    if (shown) return;
    localStorage.setItem(AUTOSAVE_INTRO_KEY, "1");
    showStatusMessage("Autosave is on for this project.");
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
  async function handleTabChange(nextKind: string): Promise<void> {
    if (nextKind !== "kuro" && nextKind !== "mame") {
      return;
    }

    const target: AutosaveTarget = {
      projectPath: project?.path ?? null,
      scratch: project?.scratch ?? true,
    };
    await flushAutosave(target, nextKind === "kuro" ? "mame" : "kuro");

    void rpc(nextKind as SidecarKind, "ping", {}).catch(() => {
      // Ignore lazy sidecar startup failures in the shell.
    });
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
            Memory: {Math.round(memoryWarning.ratio * 100)}% (sidecar {memoryWarning.rss_mb.toFixed(0)} MB)
          </span>
          <button
            type="button"
            aria-label="메모리 경고 닫기"
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
              메모리 한계 초과
            </h2>
            <p id="mem-block-desc" className="mb-4 text-sm text-muted-foreground">
              Sidecar 프로세스 메모리 사용량이{" "}
              {Math.round(memoryWarning.ratio * 100)}% ({memoryWarning.rss_mb.toFixed(0)} MB)에
              도달했습니다. 진행 중인 작업을 중단하고 앱을 재시작해 주세요.
            </p>
            <button
              type="button"
              className="w-full rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setMemoryWarning(null)}
            >
              확인
            </button>
          </div>
        </div>
      )}

      <Tabs defaultValue="kuro" onValueChange={(v) => { void handleTabChange(v); }} className="flex min-h-0 flex-1 flex-col">
        <header className="h-header flex shrink-0 items-center border-b bg-background px-4">
          <div className="flex w-full min-w-0 items-center gap-4">
            <span className="shrink-0 text-lg font-semibold tracking-tight text-foreground">kuma</span>
            <TabsList className="h-10 shrink-0 rounded-xl border border-border bg-accent/70 p-1 shadow-sm">
              <TabsTrigger value="kuro" className="min-w-20 px-4 data-[state=active]:shadow-sm">Kuro</TabsTrigger>
              <TabsTrigger value="mame" className="min-w-20 px-4 data-[state=active]:shadow-sm">Mame</TabsTrigger>
            </TabsList>
            <div className="min-w-0 flex-1 border-l border-border/80 pl-4 text-caption text-muted-foreground">
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
                aria-label={`Autosave: ${autosaveLabel}`}
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
                      setAutosaveLabel("Autosave on");
                    }}
                    aria-label="Retry autosave"
                  >
                    retry
                  </button>
                )}
              </span>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-hidden">
          <TabsContent value="kuro" className="mt-0 h-full overflow-hidden">
            <KuroTab />
          </TabsContent>
          <TabsContent value="mame" className="mt-0 h-full overflow-hidden">
            <MameTab />
          </TabsContent>
        </div>
      </Tabs>

      <div
        className="fixed bottom-10 left-1/2 z-50 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-background/95 px-2 py-1 text-caption shadow-md backdrop-blur-sm"
        aria-label="Floating panel visibility controls"
      >
        <span className="px-1 text-muted-foreground">Panels</span>
        <button
          type="button"
          className={`rounded-full px-2 py-0.5 font-medium transition-colors ${
            logPanelVisible
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
          onClick={() => setLogPanelVisible((v) => !v)}
          aria-pressed={logPanelVisible}
          title="Log: sidecar progress messages"
        >
          Log
        </button>
        <button
          type="button"
          className={`rounded-full px-2 py-0.5 font-medium transition-colors ${
            jobsPanelVisible
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
          onClick={() => setJobsPanelVisible((v) => !v)}
          aria-pressed={jobsPanelVisible}
          title="Jobs: queued background tasks"
        >
          Jobs
        </button>
      </div>

      {/* §13 Background Job Queue floating panel */}
      {jobsPanelVisible && (
        <JobQueuePanel onClose={() => setJobsPanelVisible(false)} />
      )}

      {/* §2 Observability: sidecar log panel */}
      {logPanelVisible && (
        <LogPanel onClose={() => setLogPanelVisible(false)} />
      )}

      {/* §22 Graceful Shutdown: busy 상태 close 확인 */}
      <CloseConfirmDialog
        open={closeDialogOpen}
        reason={closeBusyReason}
        isBusy={closeDialogIsBusy}
        onWait={handleCloseWait}
        onForceClose={handleForceClose}
      />
    </div>
  );
}
