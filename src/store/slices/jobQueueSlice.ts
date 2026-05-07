/**
 * §13 Background Job Queue
 *
 * Sequential job queue — one job runs at a time. Additional jobs wait as
 * "pending" and are automatically started when the current job finishes.
 *
 * Design decisions:
 * - AbortController per job: `run(signal)` receives an AbortSignal so callers
 *   can hook into `signal.addEventListener("abort", ...)` for cooperative
 *   cancellation. This is forward-compatible with future sidecar cancel RPCs.
 * - `isProcessing` private flag (module-level ref) prevents concurrent
 *   processNext calls from picking up the same pending job.
 * - No circular store import: this slice is self-contained.
 */

import type { StateCreator } from "zustand";
import type { AppState } from "../types";

// ── Public types ─────────────────────────────────────────────────────────────

export type JobKind = "design" | "export" | "analyze" | "merge";
export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Job {
  id: string;
  kind: JobKind;
  /** User-facing display label */
  label: string;
  startedAt?: number;
  finishedAt?: number;
  status: JobStatus;
  errorMessage?: string;
}

export interface JobQueueSlice {
  // ── State
  jobs: Job[];

  // ── Actions
  /**
   * Add a job to the queue and start processing if idle.
   * @param kind  Job category (for icon display)
   * @param label User-visible description
   * @param run   Async work function that receives an AbortSignal
   * @returns     The assigned job id
   */
  enqueueJob: (
    kind: JobKind,
    label: string,
    run: (signal: AbortSignal) => Promise<void>,
  ) => Promise<string>;

  /**
   * Cancel a job.
   * - pending  → immediately set to cancelled
   * - running  → abort signal fired; final status set to cancelled
   * - completed/failed/cancelled → no-op
   */
  cancelJob: (id: string) => void;

  /** Remove all completed, failed, and cancelled jobs from the list */
  clearCompleted: () => void;
}

// ── Module-level concurrency guard ──────────────────────────────────────────

/** True while a job's run() Promise is in flight */
let isProcessing = false;

/**
 * AbortController map: id → controller.
 * Kept outside the store so we never serialise DOM objects into Zustand state.
 */
const controllers = new Map<string, AbortController>();

// ── Slice factory ────────────────────────────────────────────────────────────

export const createJobQueueSlice: StateCreator<
  AppState,
  [],
  [],
  JobQueueSlice
> = (set, get) => {
  // ── processNext: internal sequential processor
  function processNext(): void {
    if (isProcessing) return;

    const pending = get().jobs.find((j) => j.status === "pending");
    if (!pending) return;

    isProcessing = true;

    // Create AbortController for this job
    const controller = new AbortController();
    controllers.set(pending.id, controller);

    // Mark as running
    set((s) => ({
      jobs: s.jobs.map((j) =>
        j.id === pending.id
          ? { ...j, status: "running" as JobStatus, startedAt: Date.now() }
          : j,
      ),
    }));

    // Retrieve the run function stored on the job record
    // We store it in a side-channel map (not in Zustand state) to avoid
    // serialising functions into the store snapshot.
    const runFn = runRegistry.get(pending.id);
    if (!runFn) {
      // Should never happen; guard against race conditions
      set((s) => ({
        jobs: s.jobs.map((j) =>
          j.id === pending.id
            ? {
                ...j,
                status: "failed" as JobStatus,
                finishedAt: Date.now(),
                errorMessage: "Internal: run function not found",
              }
            : j,
        ),
      }));
      isProcessing = false;
      processNext();
      return;
    }

    // Wrap in Promise.resolve() to guard against sync throws from
    // hand-rolled run functions (async functions never throw sync,
    // but defensive hardening prevents an isProcessing deadlock).
    Promise.resolve()
      .then(() => runFn(controller.signal))
      .then(() => {
        const wasCancelled = controller.signal.aborted;
        set((s) => ({
          jobs: s.jobs.map((j) =>
            j.id === pending.id
              ? {
                  ...j,
                  status: wasCancelled
                    ? ("cancelled" as JobStatus)
                    : ("completed" as JobStatus),
                  finishedAt: Date.now(),
                }
              : j,
          ),
        }));
      })
      .catch((err: unknown) => {
        const wasCancelled = controller.signal.aborted;
        const message =
          err instanceof Error ? err.message : String(err);
        set((s) => ({
          jobs: s.jobs.map((j) =>
            j.id === pending.id
              ? {
                  ...j,
                  status: wasCancelled
                    ? ("cancelled" as JobStatus)
                    : ("failed" as JobStatus),
                  finishedAt: Date.now(),
                  errorMessage: wasCancelled ? undefined : message,
                }
              : j,
          ),
        }));
      })
      .finally(() => {
        runRegistry.delete(pending.id);
        controllers.delete(pending.id);
        isProcessing = false;
        processNext();
      });
  }

  return {
    jobs: [],

    enqueueJob: async (kind, label, run) => {
      const id = `job-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

      // Store run function outside Zustand state
      runRegistry.set(id, run);

      const newJob: Job = {
        id,
        kind,
        label,
        status: "pending",
      };

      set((s) => ({ jobs: [...s.jobs, newJob] }));

      // Kick off processing (no-op if already running)
      processNext();

      return id;
    },

    cancelJob: (id) => {
      const job = get().jobs.find((j) => j.id === id);
      if (!job) return;
      if (
        job.status === "completed" ||
        job.status === "failed" ||
        job.status === "cancelled"
      ) {
        return;
      }

      if (job.status === "pending") {
        // Cancel immediately — no run function started
        runRegistry.delete(id);
        set((s) => ({
          jobs: s.jobs.map((j) =>
            j.id === id
              ? { ...j, status: "cancelled" as JobStatus, finishedAt: Date.now() }
              : j,
          ),
        }));
        return;
      }

      // Running — fire the abort signal; the finally block in processNext
      // will update the status once the Promise resolves/rejects.
      const controller = controllers.get(id);
      if (controller) {
        controller.abort();
      }
    },

    clearCompleted: () => {
      set((s) => ({
        jobs: s.jobs.filter(
          (j) =>
            j.status !== "completed" &&
            j.status !== "failed" &&
            j.status !== "cancelled",
        ),
      }));
    },
  };
};

// ── Run function registry (module-level, outside Zustand) ────────────────────
// Functions cannot be stored in Zustand state (snapshot/serialisation issues).
const runRegistry = new Map<string, (signal: AbortSignal) => Promise<void>>();
