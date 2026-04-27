import { useEffect, useState } from "react";
import { getConfig, loadProject, type Config } from "./lib/project";
import { MainShell } from "./screens/MainShell";
import { Home } from "./screens/Home";
import { Onboarding } from "./screens/Onboarding";
import { ProjectProvider, type KumaProject } from "./state/projectContext";

type AppScreen = "loading" | "onboarding" | "home" | "workspace";

function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function stem(path: string): string {
  return basename(path).replace(/\.[^.]+$/, "");
}

export function App() {
  const [screen, setScreen] = useState<AppScreen>("loading");
  const [config, setConfig] = useState<Config | null>(null);
  const [project, setProject] = useState<KumaProject>(null);

  useEffect(() => {
    let isMounted = true;

    void getConfig()
      .then((cfg) => {
        if (!isMounted) {
          return;
        }
        setConfig(cfg);
        setScreen("home");
      })
      .catch(() => {
        if (isMounted) {
          setScreen("onboarding");
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      const path = custom.detail?.path;
      if (!path) {
        return;
      }
      void handleOpenWorkspace(path, false);
    };

    window.addEventListener("kuma:project-load-request", handler as EventListener);
    return () => {
      window.removeEventListener("kuma:project-load-request", handler as EventListener);
    };
  }, []);

  function handleDone(cfg: Config) {
    setConfig(cfg);
    setScreen("home");
  }

  async function handleOpenWorkspace(path: string, scratch: boolean) {
    if (scratch) {
      setProject({
        path,
        name: stem(path),
        scratch: true,
      });
      setScreen("workspace");
      return;
    }

    const fallbackProject: Exclude<KumaProject, null> = {
      path,
      name: stem(path),
      scratch: false,
    };

    try {
      const loadedProject = await loadProject(path);
      setProject({
        ...fallbackProject,
        name: loadedProject.name,
        ...(typeof loadedProject.project_id === "string" ? { project_id: loadedProject.project_id } : {}),
        ...(typeof loadedProject.stage === "string" ? { stage: loadedProject.stage } : {}),
      });
    } catch {
      setProject(fallbackProject);
    }

    setScreen("workspace");
  }

  if (screen === "loading") {
    return <div className="flex min-h-screen items-center justify-center bg-muted text-sm text-muted-foreground">Loading…</div>;
  }

  if (screen === "onboarding") {
    return <Onboarding initialPath={config?.projects_root} onDone={handleDone} />;
  }

  if (screen === "home") {
    return (
      <Home
        onOpenProject={(path) => void handleOpenWorkspace(path, false)}
        onOpenScratch={(path) => void handleOpenWorkspace(path, true)}
        onOpenSettings={() => setScreen("onboarding")}
      />
    );
  }

  return (
    <ProjectProvider value={project}>
      <MainShell />
    </ProjectProvider>
  );
}
