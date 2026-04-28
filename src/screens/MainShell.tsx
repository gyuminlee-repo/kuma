import { useEffect, useState, useCallback } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { rpc, type SidecarKind } from "@/lib/ipc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKumaProject } from "@/state/projectContext";
import { flushAutosave, type AutosaveTarget } from "@/lib/autosave";
import { useKuroAutosave } from "@/hooks/useKuroAutosave";
import { useAutosaveHydration, type HydrationStatusMessage } from "@/hooks/useAutosaveHydration";
import { KuroTab } from "./KuroTab";
import { MameTab } from "./MameTab";

export function MainShell() {
  const project = useKumaProject();
  const projectName = project ? `${project.name}${project.scratch ? " (Scratch)" : ""}` : "Workspace";

  // Phase 4: 복원 알림 (4초 후 자동 소멸). Phase 5에서 정식 autosave 슬롯으로 대체.
  const [restoreNotice, setRestoreNotice] = useState<HydrationStatusMessage | null>(null);

  const handleHydrationMessage = useCallback((msg: HydrationStatusMessage) => {
    setRestoreNotice(msg);
    setTimeout(() => setRestoreNotice(null), 4000);
  }, []);

  // Phase 2: Kuro 자동 저장 구독 등록
  useKuroAutosave();
  // Phase 4: 프로젝트 진입 시 자동 저장 복원
  useAutosaveHydration(handleHydrationMessage);

  // C-3: 윈도우 close 직전 flush (kuro + mame 양쪽)
  // mame Phase 2 완료 후에도 flushAutosave(target) (kind 미지정) 형태로 양쪽 처리됨
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

  // C-2: 탭 전환 직전 flush
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
                {/* Phase 4 임시 복원 알림. Phase 5에서 정식 autosave 슬롯으로 대체됨. */}
                {restoreNotice !== null ? (
                  <span
                    role="status"
                    aria-live="polite"
                    className="ml-2 shrink-0 truncate text-caption text-muted-foreground"
                  >
                    {restoreNotice.message}
                  </span>
                ) : null}
              </div>
            </div>
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
