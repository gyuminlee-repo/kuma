import React from "react";
import ReactDOM from "react-dom/client";
import { AppLayout } from "./components/layout/AppLayout";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppLayout />
  </React.StrictMode>,
);

if (import.meta.env.DEV) {
  import("./store/appStore").then(({ useAppStore }) => {
    (window as unknown as Record<string, unknown>).__store = useAppStore;
  });
}
