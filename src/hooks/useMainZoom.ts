/**
 * useMainZoom — main content area zoom control.
 *
 * [source: spec Phase F — F3 main 콘텐츠 zoom + localStorage]
 *
 * - Range: 1.0 – 2.0 (no zoom-out below 100%)
 * - Step: 0.1 per notch / keypress
 * - Persists to localStorage "kuma.mainZoom"
 * - Ctrl+wheel on #major-step-main
 * - Ctrl+= / Ctrl++ → zoom in
 * - Ctrl+- → zoom out
 * - Ctrl+0 → reset to 1.0
 * - CSS `zoom` property (Tauri Chromium webview supports it)
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "kuma.mainZoom";
const MIN_ZOOM = 1.0;
const MAX_ZOOM = 2.0;
const ZOOM_STEP = 0.1;

function clamp(value: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, parseFloat(value.toFixed(2))));
}

export function useMainZoom(): number {
  const [zoom, setZoom] = useState<number>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = parseFloat(stored);
        if (!isNaN(parsed)) return clamp(parsed);
      }
    } catch {
      // localStorage unavailable (SSR / sandboxed) — fall through to default
    }
    return MIN_ZOOM;
  });

  // Persist to localStorage whenever zoom changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(zoom));
    } catch {
      // Ignore write failures in restricted environments
    }
  }, [zoom]);

  // Ctrl+wheel listener on #major-step-main
  useEffect(() => {
    const handler = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setZoom((z) => clamp(e.deltaY < 0 ? z + ZOOM_STEP : z - ZOOM_STEP));
    };

    const el = document.getElementById("major-step-main");
    el?.addEventListener("wheel", handler, { passive: false });
    return () => {
      el?.removeEventListener("wheel", handler);
    };
  }, []);

  // Keyboard shortcuts: Ctrl+= / Ctrl++ / Ctrl+- / Ctrl+0
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;

      // Skip when an input/select/textarea has focus
      const tag = (e.target as Element)?.tagName;
      const isEditable =
        tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if (isEditable) return;

      switch (e.key) {
        case "=":
        case "+":
          e.preventDefault();
          setZoom((z) => clamp(z + ZOOM_STEP));
          break;
        case "-":
          e.preventDefault();
          setZoom((z) => clamp(z - ZOOM_STEP));
          break;
        case "0":
          e.preventDefault();
          setZoom(MIN_ZOOM);
          break;
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, []);

  return zoom;
}
