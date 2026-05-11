/**
 * LogPanel — §2 Observability: Sidecar log viewer
 *
 * Collapsible panel that shows real-time progress messages from the sidecar.
 * Lines are sourced from appStore.logLines (fed by progress notifications).
 *
 * Accessibility:
 * - role="region" with aria-label
 * - aria-expanded on the toggle button
 * - Log content region is aria-live="polite" when expanded
 * - "Copy all" action includes aria-label
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type { PointerEvent } from "react";
import { useAppStore } from "@/store/appStore";
import { Button } from "@/components/ui/button";

// ── Main component ────────────────────────────────────────────────────────────

interface FloatingPanelPosition {
  x: number;
  y: number;
}

interface LogPanelProps {
  onClose?: () => void;
}

const POSITION_STORAGE_KEY = "kuma:floating-panel:log:position";
const PANEL_WIDTH = 288;
const PANEL_HEIGHT_GUESS = 280;

function defaultPosition(): FloatingPanelPosition {
  if (typeof window === "undefined") return { x: 360, y: 88 };
  return {
    x: Math.min(360, Math.max(12, window.innerWidth - PANEL_WIDTH - 12)),
    y: 88,
  };
}

function clampPosition(pos: FloatingPanelPosition): FloatingPanelPosition {
  if (typeof window === "undefined") return pos;
  return {
    x: Math.min(Math.max(12, pos.x), Math.max(12, window.innerWidth - PANEL_WIDTH - 12)),
    y: Math.min(Math.max(12, pos.y), Math.max(12, window.innerHeight - PANEL_HEIGHT_GUESS)),
  };
}

function readPosition(): FloatingPanelPosition {
  if (typeof window === "undefined") return defaultPosition();
  const raw = window.localStorage.getItem(POSITION_STORAGE_KEY);
  if (!raw) return defaultPosition();
  try {
    const parsed = JSON.parse(raw) as Partial<FloatingPanelPosition>;
    if (typeof parsed.x === "number" && typeof parsed.y === "number") {
      return clampPosition({ x: parsed.x, y: parsed.y });
    }
  } catch {
    // Ignore malformed persisted UI state.
  }
  return defaultPosition();
}

export function LogPanel({ onClose }: LogPanelProps) {
  const logLines = useAppStore((s) => s.logLines);
  const clearLogLines = useAppStore((s) => s.clearLogLines);

  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [position, setPosition] = useState<FloatingPanelPosition>(() => readPosition());
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  // Auto-scroll: follow bottom unless user has scrolled up
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

  // Detect manual scroll-up
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
    userScrolledUpRef.current = !atBottom;
  }, []);

  // Auto-scroll to bottom on new lines when user hasn't scrolled up
  useEffect(() => {
    if (!expanded) return;
    if (userScrolledUpRef.current) return;
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logLines, expanded]);

  // When panel expands, scroll to bottom
  useEffect(() => {
    if (!expanded) return;
    userScrolledUpRef.current = false;
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [expanded]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(position));
  }, [position]);

  const handlePointerDown = useCallback((event: PointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const target = event.target;
    if (target instanceof Element && target.closest("button")) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: position.x,
      originY: position.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, [position]);

  const handlePointerMove = useCallback((event: PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setPosition(clampPosition({
      x: drag.originX + event.clientX - drag.startX,
      y: drag.originY + event.clientY - drag.startY,
    }));
  }, []);

  const handlePointerUp = useCallback((event: PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  async function handleCopyAll() {
    const text = logLines.join("\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const lineCount = logLines.length;

  return (
    <section
      className="fixed z-40 w-72 rounded-xl border border-border bg-background/95 shadow-lg backdrop-blur-sm"
      style={{ left: position.x, top: position.y }}
      aria-label="Sidecar log panel"
    >
      {/* Header / toggle row */}
      <div
        className="flex w-full cursor-move items-center justify-between rounded-xl px-3 py-2 text-xs font-medium text-foreground hover:bg-accent/60 transition-colors"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <span className="flex min-w-0 items-center gap-1.5" title="Sidecar progress log. Drag to move.">
          <span
            className="h-2 w-2 rounded-full shrink-0 bg-muted-foreground/40"
            aria-hidden="true"
          />
          <span>Log ({lineCount})</span>
        </span>
        <span className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="rounded px-1 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => { setExpanded((v) => !v); }}
            aria-expanded={expanded}
            aria-controls="log-panel-content"
            aria-label="Toggle sidecar log panel"
          >
            {expanded ? "▲" : "▼"}
          </button>
          {onClose && (
            <button
              type="button"
              className="rounded px-1 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={onClose}
              aria-label="Hide sidecar log panel"
            >
              ×
            </button>
          )}
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div
          id="log-panel-content"
          className="border-t border-border"
        >
          {/* Log lines scroll area */}
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="max-h-48 overflow-y-auto px-2 pt-1.5 pb-0"
            role="log"
            aria-label="Sidecar log messages"
            aria-live="polite"
            aria-atomic="false"
            aria-relevant="additions"
          >
            {lineCount === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                No log messages yet
              </p>
            ) : (
              <ul className="list-none p-0 m-0 space-y-0.5">
                {logLines.map((line, idx) => (
                  <li
                    // stable key combining index + content hash is acceptable for append-only logs
                    key={idx}
                    className="text-xs font-mono text-muted-foreground leading-tight break-all whitespace-pre-wrap"
                  >
                    {line}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Footer actions */}
          <div className="flex items-center justify-between border-t border-border px-2 py-1.5">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => { clearLogLines(); userScrolledUpRef.current = false; }}
              aria-label="Clear all log messages"
              disabled={lineCount === 0}
            >
              Clear
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => { void handleCopyAll(); }}
              aria-label="Copy all log messages to clipboard"
              disabled={lineCount === 0}
            >
              {copied ? "Copied!" : "Copy all"}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
