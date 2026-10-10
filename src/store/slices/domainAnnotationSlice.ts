import type { StateCreator } from "zustand";
import i18next from "i18next";
import type { AppState } from "../types";
import type { DomainAnnotationAttempt, DomainAnnotationJob, DomainAnnotationResult, DomainAnnotationSource, DomainRuntimeStatus } from "@/types/domainAnnotation";
import { sendRequest } from "@/lib/ipc-kuro";
import { formatError } from "@/lib/utils";
import { bindingMatchesSource, domainAnnotationContextKey, domainAnnotationSource, domainJobIsActive, hashDomainReference, sameDomainBinding } from "@/lib/domainAnnotation";

export interface DomainAnnotationSlice {
  domainRuntimeStatus: DomainRuntimeStatus | null;
  domainRuntimeLoading: boolean;
  domainAnnotationJob: DomainAnnotationJob | null;
  domainAnnotationAttempt: DomainAnnotationAttempt | null;
  domainAnnotationResult: DomainAnnotationResult | null;
  domainAnnotationContext: string | null;
  domainAnnotationPending: "starting" | "importing" | "cancelling" | null;
  domainAnnotationError: string | null;
  refreshDomainRuntime: () => Promise<void>;
  installDomainRuntime: (archivePath: string) => Promise<void>;
  removeDomainRuntime: () => Promise<void>;
  startDomainAnnotation: () => Promise<void>;
  pollDomainAnnotation: () => Promise<void>;
  cancelDomainAnnotation: () => Promise<void>;
  importDomainAnnotationFile: (filepath: string) => Promise<void>;
  resetDomainAnnotation: () => void;
}

/** Separate session-only state: annotation never participates in scientific selection or persistence. */
export const createDomainAnnotationSlice: StateCreator<AppState, [], [], DomainAnnotationSlice> = (set, get) => {
  let generation = 0;
  let runtimeGeneration = 0;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let pollingJob: string | null = null;
  let cancellingJob: string | null = null;
  let activeAttemptId: string | null = null;
  let attemptCancellationRequested = false;
  let activeContext: string | null = null;
  let activeGeneration = 0;

  function clearPoll() { if (pollTimer !== null) clearTimeout(pollTimer); pollTimer = null; }
  function busy() { return Boolean(get().domainAnnotationPending || domainJobIsActive(get().domainAnnotationJob?.state)); }
  function schedulePoll() {
    clearPoll();
    if (domainJobIsActive(get().domainAnnotationJob?.state) || (activeAttemptId && get().domainAnnotationPending))
      pollTimer = setTimeout(() => { void get().pollDomainAnnotation(); }, 1500);
  }
  function current(token: number, context: string) { return token === generation && context === domainAnnotationContextKey(get()); }
  async function validateResult(result: DomainAnnotationResult, source: DomainAnnotationSource, job?: DomainAnnotationJob) {
    const referenceHash = await hashDomainReference(source.ref_seq);
    if (!bindingMatchesSource(result.binding, source, referenceHash) || result.total_residues !== source.ref_seq.length
      || (job && (result.job_id !== job.job_id || result.provenance !== "managed" || !sameDomainBinding(result.binding, job.binding)))
      || (!job && (result.provenance !== "imported" || result.job_id !== null))) {
      throw new Error(i18next.t("optionalDomains.identityMismatch"));
    }
  }
  async function acceptJob(job: DomainAnnotationJob) {
    const previous = get().domainAnnotationJob;
    if (previous && (job.job_id !== previous.job_id || !sameDomainBinding(job.binding, previous.binding))) {
      throw new Error(i18next.t("optionalDomains.identityMismatch"));
    }
    if (previous && !domainJobIsActive(previous.state)) return;
    if (previous?.state === "cancelling" && (job.state === "queued" || job.state === "running")) { schedulePoll(); return; }
    set({ domainAnnotationJob: job });
    if (domainJobIsActive(job.state)) { schedulePoll(); return; }
    clearPoll();
    set({ domainAnnotationPending: null });
    if (job.state === "failed") { set({ domainAnnotationError: job.message }); return; }
    if (job.state !== "succeeded" || activeContext === null || !current(activeGeneration, activeContext)) return;
    const source = domainAnnotationSource(get());
    if (!source) return;
    const token = activeGeneration;
    const context = activeContext;
    set({ domainAnnotationPending: "importing" });
    try {
      const result = await sendRequest("import_domain_annotation_result", { ...source, job_id: job.job_id });
      if (!current(token, context) || get().domainAnnotationJob?.job_id !== job.job_id) return;
      await validateResult(result, source, job);
      if (!current(token, context) || get().domainAnnotationJob?.job_id !== job.job_id) return;
      set({ domainAnnotationResult: result, domainAnnotationContext: context, domainAnnotationError: null });
    } catch (error) {
      if (current(token, context)) set({ domainAnnotationError: formatError(error) });
    } finally {
      if (current(token, context)) set({ domainAnnotationPending: null });
    }
  }
  async function acceptAttempt(attempt: DomainAnnotationAttempt) {
    if (attempt.attempt_id !== activeAttemptId) throw new Error(i18next.t("optionalDomains.identityMismatch"));
    const previous = get().domainAnnotationAttempt;
    if (previous && ["cancelled", "failed", "expired"].includes(previous.state)) return;
    set({ domainAnnotationAttempt: attempt });
    if (attempt.state === "job" && attempt.job) {
      await acceptJob(attempt.job);
      return;
    }
    if (attempt.state === "pending" || attempt.state === "unknown") { schedulePoll(); return; }
    clearPoll();
    set({ domainAnnotationPending: null });
    if (attempt.state === "failed" || attempt.state === "expired") set({ domainAnnotationError: attempt.message });
  }
  async function runtimeOperation(operation: "status" | "install" | "remove", archivePath?: string) {
    if (get().domainRuntimeLoading || busy()) return;
    if (operation === "install" && !get().domainRuntimeStatus?.install_available) return;
    const token = ++runtimeGeneration;
    set({ domainRuntimeLoading: true, domainAnnotationError: null });
    try {
      const status = operation === "install"
        ? await sendRequest("domain_runtime_install", { archive_path: archivePath ?? "" }, 120_000)
        : operation === "remove" ? await sendRequest("domain_runtime_remove", {}) : await sendRequest("domain_runtime_status", {});
      if (token === runtimeGeneration) set({ domainRuntimeStatus: status });
    } catch (error) {
      if (token === runtimeGeneration) set({ domainRuntimeStatus: null, domainAnnotationError: formatError(error) });
    } finally {
      if (token === runtimeGeneration) set({ domainRuntimeLoading: false });
    }
  }

  return {
    domainRuntimeStatus: null, domainRuntimeLoading: false, domainAnnotationJob: null, domainAnnotationAttempt: null,
    domainAnnotationResult: null, domainAnnotationContext: null, domainAnnotationPending: null, domainAnnotationError: null,
    refreshDomainRuntime: () => runtimeOperation("status"),
    installDomainRuntime: (archivePath) => runtimeOperation("install", archivePath),
    removeDomainRuntime: () => runtimeOperation("remove"),
    startDomainAnnotation: async () => {
      if (busy() || get().domainRuntimeLoading || get().domainRuntimeStatus?.state !== "installed") return;
      const source = domainAnnotationSource(get());
      if (!source) return;
      const token = ++generation;
      const attemptId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) => value.toString(16).padStart(2, "0")).join("");
      activeAttemptId = attemptId; attemptCancellationRequested = false;
      const context = domainAnnotationContextKey(get());
      activeGeneration = token; activeContext = context;
      clearPoll();
      set({ domainAnnotationPending: "starting", domainAnnotationJob: null,
        domainAnnotationAttempt: { attempt_id: attemptId, state: "pending", message: "", job: null }, domainAnnotationResult: null,
        domainAnnotationContext: null, domainAnnotationError: null });
      try {
        const job = await sendRequest("start_domain_annotation", { ...source, attempt_id: attemptId }, 120_000);
        const referenceHash = await hashDomainReference(source.ref_seq);
        if (activeAttemptId !== attemptId || get().domainAnnotationAttempt?.state === "cancelled") return;
        if (!bindingMatchesSource(job.binding, source, referenceHash)) {
          // Even an unusable binding may refer to a real process. Retain and cancel it.
          set({ domainAnnotationJob: job, domainAnnotationError: i18next.t("optionalDomains.identityMismatch") });
          await get().cancelDomainAnnotation();
          return;
        }
        set({ domainAnnotationAttempt: { attempt_id: attemptId, state: "job", message: job.message, job } });
        if (!current(token, context) || get().domainAnnotationPending === "cancelling") {
          if (!get().domainAnnotationJob) set({ domainAnnotationJob: job });
          await get().cancelDomainAnnotation();
          return;
        }
        set({ domainAnnotationPending: null });
        await acceptJob(job);
      } catch (error) {
        if (activeAttemptId !== attemptId || get().domainAnnotationAttempt?.state === "cancelled") return;
        if (current(token, context)) set({ domainAnnotationError: formatError(error) });
        // A lost response is ambiguous. Cancel the exact attempt, including any late dispatch.
        await get().cancelDomainAnnotation();
      }
    },
    pollDomainAnnotation: async () => {
      const job = get().domainAnnotationJob;
      if (!job && activeAttemptId && get().domainAnnotationPending) {
        const attemptId = activeAttemptId;
        if (pollingJob === attemptId) return;
        clearPoll(); pollingJob = attemptId;
        try {
          const attempt = await sendRequest(attemptCancellationRequested ? "cancel_domain_annotation_attempt" : "get_domain_annotation_attempt", { attempt_id: attemptId });
          if (activeAttemptId === attemptId) await acceptAttempt(attempt);
        } catch (error) {
          if (activeAttemptId === attemptId) { set({ domainAnnotationError: formatError(error) }); schedulePoll(); }
        } finally { if (pollingJob === attemptId) pollingJob = null; }
        return;
      }
      if (!job || !domainJobIsActive(job.state) || pollingJob === job.job_id) return;
      clearPoll(); pollingJob = job.job_id;
      const token = generation;
      try {
        const next = await sendRequest("poll_domain_annotation", { job_id: job.job_id });
        if (get().domainAnnotationJob?.job_id !== job.job_id) return;
        if (token !== generation) { schedulePoll(); return; }
        await acceptJob(next);
      } catch (error) {
        if (get().domainAnnotationJob?.job_id === job.job_id) {
          set({ domainAnnotationError: formatError(error) }); schedulePoll();
        }
      } finally { if (pollingJob === job.job_id) pollingJob = null; }
    },
    cancelDomainAnnotation: async () => {
      ++generation;
      set({ domainAnnotationResult: null, domainAnnotationContext: null });
      const job = get().domainAnnotationJob;
      if (!job) {
        if (!activeAttemptId || !get().domainAnnotationPending || get().domainAnnotationPending === "importing") {
          set({ domainAnnotationPending: null }); return;
        }
        const attemptId = activeAttemptId;
        attemptCancellationRequested = true;
        set({ domainAnnotationPending: "cancelling" });
        if (cancellingJob === attemptId) return;
        cancellingJob = attemptId;
        try {
          const attempt = await sendRequest("cancel_domain_annotation_attempt", { attempt_id: attemptId });
          if (activeAttemptId === attemptId) await acceptAttempt(attempt);
        } catch (error) {
          if (activeAttemptId === attemptId) { set({ domainAnnotationError: formatError(error) }); schedulePoll(); }
        } finally { if (cancellingJob === attemptId) cancellingJob = null; }
        return;
      }
      if (!domainJobIsActive(job.state)) { set({ domainAnnotationPending: null }); return; }
      set({ domainAnnotationPending: "cancelling" });
      if (cancellingJob === job.job_id) return;
      cancellingJob = job.job_id;
      try {
        const next = await sendRequest("cancel_domain_annotation", { job_id: job.job_id });
        if (get().domainAnnotationJob?.job_id !== job.job_id) return;
        await acceptJob(next);
      } catch (error) {
        if (get().domainAnnotationJob?.job_id === job.job_id) {
          set({ domainAnnotationError: formatError(error) }); schedulePoll();
        }
      } finally { if (cancellingJob === job.job_id) cancellingJob = null; }
    },
    importDomainAnnotationFile: async (filepath) => {
      if (busy() || get().domainRuntimeLoading) return;
      const source = domainAnnotationSource(get());
      if (!source) return;
      const token = ++generation;
      const context = domainAnnotationContextKey(get());
      activeAttemptId = null;
      set({ domainAnnotationPending: "importing", domainAnnotationResult: null, domainAnnotationContext: null,
        domainAnnotationJob: null, domainAnnotationAttempt: null, domainAnnotationError: null });
      try {
        const result = await sendRequest("import_domain_annotation_file", { ...source, filepath });
        if (!current(token, context)) return;
        await validateResult(result, source);
        if (!current(token, context)) return;
        set({ domainAnnotationResult: result, domainAnnotationContext: context });
      } catch (error) {
        if (current(token, context)) set({ domainAnnotationError: formatError(error) });
      } finally {
        if (current(token, context)) set({ domainAnnotationPending: null });
      }
    },
    resetDomainAnnotation: () => {
      ++generation;
      set({ domainAnnotationResult: null, domainAnnotationContext: null, domainAnnotationError: null });
      if (domainJobIsActive(get().domainAnnotationJob?.state) || get().domainAnnotationPending === "starting"
        || get().domainAnnotationPending === "cancelling") {
        void get().cancelDomainAnnotation();
      } else {
        activeAttemptId = null;
        clearPoll(); set({ domainAnnotationJob: null, domainAnnotationAttempt: null, domainAnnotationPending: null });
      }
    },
  };
};
