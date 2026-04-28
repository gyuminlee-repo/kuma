import { useEffect, useRef, useState, useCallback } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { rpc, type SidecarKind } from "@/lib/ipc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKumaProject } from "@/state/projectContext";
import { flushAutosave, onAutosaveEvent, type AutosaveTarget, type AutosaveEvent } from "@/lib/autosave";
import { useKuroAutosave } from "@/hooks/useKuroAutosave";
import { useAutosaveHydration, type HydrationStatusMessage } from "@/hooks/useAutosaveHydration";
import { Spinner } from "@/components/ui/Spinner";
import { KuroTab } from "./KuroTab";
import { MameTab } from "./MameTab";

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

// ─── autosave 상태 타입 (인디케이터 전용) ────────────────────────────────

type AutosaveIndicatorState = "idle" | "saving" | "saved" | "error";

const AUTOSAVE_DOT: Record<AutosaveIndicatorState, string> = {
  idle: "bg-success",
  saving: "bg-info",
  saved: "bg-success",
  error: "bg-error",
};

// ─── 컴포넌트 ─────────────────────────────────────────────────────────────

export function MainShell() {
  const project = useKumaProject();
  const projectName = project ? `${project.name}${project.scratch ? " (Scratch)" : ""}` : "Workspace";

  // ── 상태바 좌측 메시지 (4초 자동 소멸)
  const [statusMessage, setStatusMessage] = useState("");
  const msgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showStatusMessage = useCallback((msg: string) => {
    if (msgTimerRef.current !== null) clearTimeout(msgTimerRef.current);
    setStatusMessage(msg);
    msgTimerRef.current = setTimeout(() => setStatusMessage(""), 4000);
  }, []);

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

  // ── 윈도우 close 직전 flush (kuro + mame 양쪽)
  useEffect(() => {
    const target: AutosaveTarget = {
      projectPath: project?.path ?? null,
      scratch: project?.scratch ?? true,
    };

    let unlisten: (() => void) | undefined;
    void getCurrentWindow()
      .onCloseRequested(async (ev) => {
        ev.preventDefault();
        await flushAutosave(target);
        await getCurrentWindow().destroy();
      })
      .then((fn) => {
        unlisten = fn;
      });

    return () => {
      unlisten?.();
    };
  }, [project?.path, project?.scratch]);

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
    </div>
  );
}
