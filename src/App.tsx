import { useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { getConfig, type Config } from "./lib/project";
import { Home } from "./screens/Home";
import { Onboarding } from "./screens/Onboarding";

type AppScreen = "loading" | "onboarding" | "home" | "workspace";

declare global {
  interface Window {
    __kumaProject?: {
      path: string;
      scratch: boolean;
    };
  }
}

export function App() {
  const [screen, setScreen] = useState<AppScreen>("loading");
  const [config, setConfig] = useState<Config | null>(null);

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

  function handleDone(cfg: Config) {
    setConfig(cfg);
    setScreen("home");
  }

  function handleOpenWorkspace(path: string, scratch: boolean) {
    window.__kumaProject = { path, scratch };
    setScreen("workspace");
  }

  if (screen === "loading") {
    return <div className="flex min-h-screen items-center justify-center bg-slate-100 text-sm text-slate-500">불러오는 중...</div>;
  }

  if (screen === "onboarding") {
    return <Onboarding initialPath={config?.projects_root} onDone={handleDone} />;
  }

  if (screen === "home") {
    return (
      <Home
        onOpenProject={(path) => handleOpenWorkspace(path, false)}
        onOpenScratch={(path) => handleOpenWorkspace(path, true)}
        onOpenSettings={() => setScreen("onboarding")}
      />
    );
  }

  return <AppLayout />;
}
