import { rpc, type SidecarKind } from "@/lib/ipc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKumaProject } from "@/state/projectContext";
import { KuroTab } from "./KuroTab";
import { MameTab } from "./MameTab";

export function MainShell() {
  const project = useKumaProject();
  const projectName = project ? `${project.name}${project.scratch ? " (Scratch)" : ""}` : "Workspace";

  function handleTabChange(nextKind: string) {
    if (nextKind !== "kuro" && nextKind !== "mame") {
      return;
    }

    void rpc(nextKind as SidecarKind, "ping", {}).catch(() => {
      // Ignore lazy sidecar startup failures in the shell.
    });
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Tabs defaultValue="kuro" onValueChange={handleTabChange} className="flex min-h-0 flex-1 flex-col">
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
