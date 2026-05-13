/**
 * ResizeHandle.tsx
 *
 * 4 px drag handle placed at the right edge of the AppShell sidebar.
 * Supports mouse drag and keyboard (ArrowLeft/Right, Shift+Arrow, Home/End).
 *
 * Accessibility (spec §15.5, §15.11):
 *   role="separator" aria-orientation="vertical"
 *   aria-valuenow/min/max, tabIndex=0, aria-label via i18n key appShell.sidebarResize
 *
 * Performance (spec §15.11):
 *   mousemove callback is wrapped in requestAnimationFrame to throttle renders.
 *
 * UI Safety (spec §15.11 [권장]):
 *   During drag, cursor: col-resize + user-select: none applied to document.body.
 *   Main content pointer-events are blocked via CSS class on body.
 */

import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

interface ResizeHandleProps {
  width: number;
  min: number;
  max: number;
  onResize: (w: number) => void;
  onCommit?: () => void;
}

export function ResizeHandle({
  width,
  min,
  max,
  onResize,
  onCommit,
}: ResizeHandleProps) {
  const { t } = useTranslation();
  const dragging = useRef(false);
  const rafRef = useRef<number | null>(null);

  const clamp = useCallback(
    (v: number) => Math.max(min, Math.min(max, v)),
    [min, max],
  );

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        onResize(clamp(e.clientX));
      });
    };

    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.body.classList.remove("resizing-sidebar");
      onCommit?.();
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [clamp, onResize, onCommit]);

  const handleMouseDown = () => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    // Blocks pointer events on main content area during drag (spec §15.11 [권장])
    document.body.classList.add("resizing-sidebar");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 1;
    switch (e.key) {
      case "ArrowRight":
        e.preventDefault();
        onResize(clamp(width + step));
        break;
      case "ArrowLeft":
        e.preventDefault();
        onResize(clamp(width - step));
        break;
      case "Home":
        e.preventDefault();
        onResize(min);
        break;
      case "End":
        e.preventDefault();
        onResize(max);
        break;
    }
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-label={t("appShell.sidebarResize")}
      title={t("appShell.sidebarResize")}
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onKeyDown={handleKeyDown}
      className="absolute right-0 top-0 h-full w-1 cursor-col-resize bg-border transition-colors hover:bg-primary focus-visible:bg-primary focus-visible:outline-none"
    />
  );
}
