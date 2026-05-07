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
import { useAppStore } from "@/store/appStore";
import { Button } from "@/components/ui/button";

// ── Main component ────────────────────────────────────────────────────────────

export function LogPanel() {
  const logLines = useAppStore((s) => s.logLines);
  const clearLogLines = useAppStore((s) => s.clearLogLines);

  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

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

  async function handleCopyAll() {
    const text = logLines.join("\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const lineCount = logLines.length;

  return (
    <section
      className="fixed bottom-10 left-3 z-40 w-72 rounded-xl border border-border bg-background/95 shadow-lg backdrop-blur-sm"
      aria-label="Sidecar log panel"
    >
      {/* Header / toggle row */}
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs font-medium text-foreground hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
        onClick={() => { setExpanded((v) => !v); }}
        aria-expanded={expanded}
        aria-controls="log-panel-content"
      >
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full shrink-0 bg-muted-foreground/40"
            aria-hidden="true"
          />
          <span>Log ({lineCount})</span>
        </span>
        <span className="shrink-0 text-muted-foreground select-none" aria-hidden="true">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

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
