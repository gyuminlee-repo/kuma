/**
 * JobQueuePanel — §13 Background Job Queue UI
 *
 * Floating panel mounted in MainShell (bottom-right, above the status bar).
 * Shows a summary chip when collapsed; expands to a list of jobs with
 * kind icons, status badges, elapsed time, and cancel/clear controls.
 *
 * Accessibility:
 * - Role="region" with aria-label
 * - aria-expanded on the toggle button
 * - Status badges include screen-reader text via aria-label
 * - Running elapsed timer is aria-live="off" (numeric churn would be noisy)
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { PointerEvent } from "react";
import { useAppStore } from "@/store/appStore";
import type { Job, JobKind, JobStatus } from "@/store/slices/jobQueueSlice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { estimateETA, formatETA } from "@/lib/eta";

// ── Kind icons (text-based, no external deps) ────────────────────────────────

const KIND_ICON: Record<JobKind, string> = {
  design: "⚗",
  export: "↓",
  analyze: "◎",
  merge: "⊕",
};

const KIND_LABEL_KEY: Record<JobKind, string> = {
  design: "jobQueue.kindDesign",
  export: "jobQueue.kindExport",
  analyze: "jobQueue.kindAnalyze",
  merge: "jobQueue.kindMerge",
};

// ── Status → badge variant + label ──────────────────────────────────────────

type BadgeVariant = "default" | "secondary" | "success" | "warning" | "destructive" | "outline";

const STATUS_BADGE_VARIANT: Record<JobStatus, BadgeVariant> = {
  pending:   "secondary",
  running:   "default",
  completed: "success",
  failed:    "destructive",
  cancelled: "outline",
};

const STATUS_LABEL_KEY: Record<JobStatus, string> = {
  pending:   "jobQueue.statusPending",
  running:   "jobQueue.statusRunning",
  completed: "jobQueue.statusDone",
  failed:    "jobQueue.statusFailed",
  cancelled: "jobQueue.statusCancelled",
};

// ── Elapsed time helper ──────────────────────────────────────────────────────

function formatElapsed(startedAt: number, now: number): string {
  const sec = Math.floor((now - startedAt) / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem}s`;
}

// ── Per-job row ──────────────────────────────────────────────────────────────

function JobRow({
  job,
  now,
  progress,
  onCancel,
}: {
  job: Job;
  now: number;
  progress: number;
  onCancel: (id: string) => void;
}) {
  const { t } = useTranslation();
  const variant = STATUS_BADGE_VARIANT[job.status];
  const statusLabel = t(STATUS_LABEL_KEY[job.status]);
  const isRunning = job.status === "running";
  const isCancellable = job.status === "pending" || job.status === "running";

  const elapsed =
    isRunning && job.startedAt !== undefined
      ? formatElapsed(job.startedAt, now)
      : null;

  // ETA: only show for running jobs with some progress
  const etaMs = isRunning ? estimateETA(job.kind, progress) : null;
  const etaLabel = etaMs !== null ? formatETA(etaMs) : null;

  return (
    <li className="flex items-start gap-2 py-1.5 px-1 rounded-sm hover:bg-accent/40 transition-colors">
      {/* Kind icon */}
      <span
        className="mt-0.5 shrink-0 text-sm text-muted-foreground select-none"
        aria-hidden="true"
        title={t(KIND_LABEL_KEY[job.kind])}
      >
        {KIND_ICON[job.kind]}
      </span>

      {/* Label + meta */}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-xs font-medium text-foreground leading-tight">
          {job.label}
        </span>
        {job.errorMessage && (
          <span className="truncate text-xs text-destructive leading-tight">
            {job.errorMessage}
          </span>
        )}
      </div>

      {/* Elapsed + ETA (running only) */}
      {elapsed !== null && (
        <span
          className="flex shrink-0 flex-col items-end gap-0.5"
          aria-live="off"
        >
          <span className="text-xs tabular-nums text-muted-foreground">
            {elapsed}
          </span>
          {etaLabel && (
            <span className="text-xs text-muted-foreground/70 whitespace-nowrap">
              {etaLabel}
            </span>
          )}
        </span>
      )}

      {/* Status badge */}
      <Badge
        variant={variant}
        className="shrink-0 text-xs px-1.5 py-0"
        aria-label={t("jobQueue.statusAriaLabel", { status: statusLabel })}
      >
        {statusLabel}
      </Badge>

      {/* Cancel button */}
      {isCancellable && (
        <Button
          variant="ghost"
          size="sm"
          className="h-5 w-5 shrink-0 p-0 text-muted-foreground hover:text-destructive"
          onClick={() => { onCancel(job.id); }}
          aria-label={t("jobQueue.cancelJobAriaLabel", { label: job.label })}
        >
          ✕
        </Button>
      )}
    </li>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────

interface FloatingPanelPosition {
  x: number;
  y: number;
}

interface JobQueuePanelProps {
  onClose?: () => void;
}

const POSITION_STORAGE_KEY = "kuma:floating-panel:jobs:position";
const PANEL_WIDTH = 288;
const PANEL_HEIGHT_GUESS = 340;

function defaultPosition(): FloatingPanelPosition {
  if (typeof window === "undefined") return { x: 720, y: 88 };
  return {
    x: Math.max(12, window.innerWidth - PANEL_WIDTH - 12),
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

export function JobQueuePanel({ onClose }: JobQueuePanelProps) {
  const { t } = useTranslation();
  const jobs = useAppStore((s) => s.jobs);
  const cancelJob = useAppStore((s) => s.cancelJob);
  const clearCompleted = useAppStore((s) => s.clearCompleted);
  const progress = useAppStore((s) => s.progress);

  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(Date.now);
  const [position, setPosition] = useState<FloatingPanelPosition>(() => readPosition());
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  // Tick every second when a job is running, to update elapsed timers
  useEffect(() => {
    const hasRunning = jobs.some((j) => j.status === "running");
    if (!hasRunning) return;
    const id = setInterval(() => { setNow(Date.now()); }, 1000);
    return () => { clearInterval(id); };
  }, [jobs]);

  const handleCancel = useCallback(
    (id: string) => { cancelJob(id); },
    [cancelJob],
  );

  const handleClear = useCallback(() => { clearCompleted(); }, [clearCompleted]);

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

  const runningCount = jobs.filter((j) => j.status === "running").length;
  const pendingCount = jobs.filter((j) => j.status === "pending").length;
  const doneCount = jobs.filter(
    (j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled",
  ).length;

  const summaryLabel =
    runningCount > 0 || pendingCount > 0
      ? t("jobQueue.summaryRunning", { running: runningCount, pending: pendingCount })
      : jobs.length === 0
        ? t("jobQueue.summaryEmpty")
        : t("jobQueue.summaryDone", { done: doneCount });

  return (
    <section
      className="fixed z-40 w-72 rounded-xl border border-border bg-background/95 shadow-lg backdrop-blur-sm"
      style={{ left: position.x, top: position.y }}
      aria-label={t("jobQueue.panelAriaLabel")}
    >
      {/* Collapsed / header row */}
      <div
        className="flex w-full cursor-move items-center justify-between rounded-xl px-3 py-2 text-xs font-medium text-foreground hover:bg-accent/60 transition-colors"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <span className="flex min-w-0 items-center gap-1.5" title={t("jobQueue.dragTitle")}>
          {/* Activity indicator dot */}
          <span
            className={`h-2 w-2 rounded-full shrink-0 transition-colors ${
              runningCount > 0
                ? "bg-info animate-pulse"
                : pendingCount > 0
                  ? "bg-warning"
                  : "bg-muted-foreground/40"
            }`}
            aria-hidden="true"
          />
          <span>{summaryLabel}</span>
        </span>

        <span className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="rounded px-1 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => { setExpanded((v) => !v); }}
            aria-expanded={expanded}
            aria-controls="job-queue-list"
            aria-label={t("jobQueue.toggleAriaLabel")}
          >
            {expanded ? "▲" : "▼"}
          </button>
          {onClose && (
            <button
              type="button"
              className="rounded px-1 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={onClose}
              aria-label={t("jobQueue.hideAriaLabel")}
            >
              ×
            </button>
          )}
        </span>
      </div>

      {/* Expanded list */}
      {expanded && (
        <div
          id="job-queue-list"
          className="border-t border-border px-2 pb-2 pt-1"
        >
          {jobs.length === 0 ? (
            <p className="py-3 text-center text-xs text-muted-foreground">
              {t("jobQueue.noJobs")}
            </p>
          ) : (
            <>
              <ul
                className="max-h-56 overflow-y-auto"
                aria-label={t("jobQueue.jobListAriaLabel")}
              >
                {jobs.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    now={now}
                    progress={progress}
                    onCancel={handleCancel}
                  />
                ))}
              </ul>

              {doneCount > 0 && (
                <div className="mt-1.5 flex justify-end border-t border-border pt-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground"
                    onClick={handleClear}
                    aria-label={t("jobQueue.clearDoneAriaLabel")}
                  >
                    {t("jobQueue.clearDone", { count: doneCount })}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
