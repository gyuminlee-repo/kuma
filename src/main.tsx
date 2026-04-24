import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { appendCrashLog } from "./lib/crashLog";
import "./index.css";

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
        <div className="flex flex-col items-center justify-center h-screen bg-gray-50 text-gray-700">
          <p className="text-lg font-semibold mb-2">Something went wrong.</p>
          <button
            className="px-4 py-2 bg-gray-800 text-white rounded hover:bg-gray-700"
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);

if (import.meta.env.DEV) {
  import("./store/appStore").then(({ useAppStore }) => {
    window.__store = useAppStore;
  });
}
