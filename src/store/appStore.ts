import { create } from "zustand";
import { setProgressHandler } from "../lib/ipc-kuro";
import { createSequenceSlice } from "./slices/sequenceSlice";
import { createDiversitySlice } from "./slices/diversitySlice";
import { createInputSlice } from "./slices/inputSlice";
import { createDesignSlice } from "./slices/designSlice";
import { createExportSlice } from "./slices/exportSlice";
import { createNetworkConsentSlice } from "./slices/networkConsentSlice";
import { createMemorySlice } from "./slices/memorySlice";
import { createJobQueueSlice } from "./slices/jobQueueSlice";
import { createLogSlice } from "./slices/logSlice";
import { createNavigationSlice } from "./slices/navigationSlice";
import { recordRunDuration } from "../lib/eta";
import type { AppState } from "./types";
export type { AppState };

export const useAppStore = create<AppState>()((...a) => {
  const [set, get] = a;

  setProgressHandler((p) => {
    // §19 memory_warning notifications arrive as type="memory_warning" in params.
    // Cast to check for the discriminating field without broadening the handler type.
    const raw = p as unknown as Record<string, unknown>;
    if (raw["type"] === "memory_warning") {
      const ratio = typeof raw["ratio"] === "number" ? raw["ratio"] : 0;
      const rss_mb = typeof raw["rss_mb"] === "number" ? raw["rss_mb"] : 0;
      const level = raw["level"] === "block" ? "block" : "warn";
      set({ memoryWarning: { ratio, rss_mb, level } });
      return;
    }
    set({ progress: p.value, statusMessage: p.message });
    // §2 Observability: feed progress messages into log buffer
    if (p.message) {
      const ts = new Date().toLocaleTimeString();
      get().appendLogLine(`[${ts}] [KURO] ${p.message}`);
    }
  });

  return {
    ...createSequenceSlice(...a),
    ...createDiversitySlice(...a),
    ...createInputSlice(...a),
    ...createDesignSlice(...a),
    ...createExportSlice(...a),
    ...createNetworkConsentSlice(...a),
    ...createMemorySlice(...a),
    ...createJobQueueSlice(...a),
    ...createLogSlice(...a),
    ...createNavigationSlice(...a),
  };
});

// §2 ETA: subscribe to job completions and record durations for future ETA
useAppStore.subscribe((state, prevState) => {
  const prevJobs = prevState.jobs;
  const nextJobs = state.jobs;
  for (const job of nextJobs) {
    const prev = prevJobs.find((j) => j.id === job.id);
    if (
      prev &&
      prev.status === "running" &&
      (job.status === "completed" || job.status === "failed") &&
      job.startedAt !== undefined &&
      job.finishedAt !== undefined
    ) {
      const duration = job.finishedAt - job.startedAt;
      recordRunDuration(job.kind, duration);
    }
  }
});
