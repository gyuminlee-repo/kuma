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
    <div className="flex h-screen flex-col bg-slate-100">
      <Tabs defaultValue="kuro" onValueChange={handleTabChange} className="flex min-h-0 flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="text-lg font-semibold tracking-tight text-slate-900">kuma</span>
              <div className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
                <span className="truncate font-medium text-slate-800">{projectName}</span>
                {project?.stage ? (
                  <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {project.stage}
                  </span>
                ) : null}
              </div>
            </div>
            <TabsList>
              <TabsTrigger value="kuro">Kuro</TabsTrigger>
              <TabsTrigger value="mame">Mame</TabsTrigger>
            </TabsList>
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
