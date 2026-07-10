import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { App } from "./App";
import { UpdateAvailableDialog } from "./components/dialogs/UpdateAvailableDialog";
import { appendCrashLog } from "./lib/crashLog";
import { initI18n, resolveActiveLocale } from "./lib/i18n";
import { restorePersistedWorkspace } from "./lib/workspace";
import "./index.css";

// i18n 초기화는 렌더 직전 bootstrap()에서 await 한다 (활성 로케일 청크 로드 후 마운트).

// Restore artifact registry from last session (no-op if absent or path gone).
void restorePersistedWorkspace().catch(() => {
  // best-effort: never block app boot on registry restore
});

declare global {
  interface Window {
    __store?: unknown;
  }
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
    appendCrashLog({
      component: "ErrorBoundary",
      message: error.message,
      stack: (error.stack ?? "") + "\n--- Component Stack ---\n" + (info.componentStack ?? ""),
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen bg-muted text-muted-foreground">
          <p className="text-lg font-semibold mb-2">Something went wrong.</p>
          <button
            className="px-4 py-2 bg-foreground text-background rounded-control hover:bg-foreground/90"
            onClick={() => window.location.reload()}
          >
            Click to reload.
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const container = document.getElementById("root");
if (!container) throw new Error("root element not found");

let root: Root;
if (import.meta.hot?.data.root) {
  root = import.meta.hot.data.root as Root;
} else {
  root = createRoot(container);
  if (import.meta.hot) import.meta.hot.data.root = root;
}

async function bootstrap(): Promise<void> {
  // 활성 로케일 리소스가 준비된 뒤 마운트해 영어 깜빡임을 방지한다.
  await initI18n(resolveActiveLocale());
  root.render(
    <React.StrictMode>
      <ErrorBoundary>
        <>
          <App />
          <UpdateAvailableDialog />
        </>
      </ErrorBoundary>
    </React.StrictMode>,
  );
}

void bootstrap();

if (import.meta.env.DEV) {
  import("./store/appStore").then(({ useAppStore }) => {
    window.__store = useAppStore;
  });
}
