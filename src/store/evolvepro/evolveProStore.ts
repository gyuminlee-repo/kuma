import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  cancelEvolveProRun,
  detectEvolveProEnv,
  esm2CheckInstalled,
  esm2DownloadCancel,
  esm2DownloadStart,
  getEmbeddingCacheStatus,
  getRunResult,
  recommendEsm2Model,
  setProgressHandler,
  startEvolveProRun,
} from "@/lib/ipc-evolvepro";
import type {
  Esm2DownloadProgress,
  Esm2ModelRecommendation,
  Esm2RecommendationResponse,
  EvolveProDetectResponse,
  EvolveProEmbeddingCacheStatusResponse,
  EvolveProRunProgress,
  EvolveProRunRequest,
  EvolveProRunResult,
  EvolveProRunResultResponse,
} from "@/types/models.evolvepro";

export type EvolveProErrorKind =
  | "env_not_found"
  | "network"
  | "disk_full"
  | "permission"
  | "runtime_error"
  | "cancelled"
  | "unknown";

export interface EvolveProErrorInfo {
  kind: EvolveProErrorKind;
  message: string;
}

function classifyError(message: string): EvolveProErrorKind {
  const m = message.toLowerCase();
  if (m.includes("env") && (m.includes("not found") || m.includes("missing"))) return "env_not_found";
  if (m.includes("network") || m.includes("connection") || m.includes("dns")) return "network";
  if (m.includes("disk") || m.includes("no space") || m.includes("enospc")) return "disk_full";
  if (m.includes("permission") || m.includes("eacces") || m.includes("denied")) return "permission";
  if (m.includes("runtime") || m.includes("subprocess") || m.includes("exit")) return "runtime_error";
  return "unknown";
}

/**
 * Returns true if the exit message represents a user-initiated cancellation.
 * Covers:
 *  - Windows STATUS_CONTROL_C_EXIT (0xC000013A = 3221225786)
 *  - Unix SIGTERM (exit code -15 / 143), SIGINT (exit code -2 / 130)
 */
function isCancelExit(message: string): boolean {
  const m = message.toLowerCase();
  return (
    m.includes("3221225786") ||
    m.includes("0xc000013a") ||
    m.includes("exit code -15") ||
    m.includes("exit code 143") ||
    m.includes("exit code -2") ||
    m.includes("exit code 130") ||
    m.includes("sigterm") ||
    m.includes("sigint")
  );
}

export type Esm2DownloadStatus = "idle" | "downloading" | "done" | "cancelled" | "error";

export interface Esm2DownloadState {
  status: Esm2DownloadStatus;
  bytes: number;
  total: number;
  error?: string;
}

const SIZE_ORDER = [
  "esm2_t6_8M_UR50D",
  "esm2_t12_35M_UR50D",
  "esm2_t30_150M_UR50D",
  "esm2_t33_650M_UR50D",
  "esm2_t36_3B_UR50D",
  "esm2_t48_15B_UR50D",
] as const;

export interface EvolveProState {
  evolveProEnvStatus: EvolveProDetectResponse | null;
  evolveProRunId: string | null;
  esm2Recommendation: Esm2RecommendationResponse | null;
  evolveProProgress: EvolveProRunProgress | null;
  evolveProResult: EvolveProRunResult | null;
  /** Detailed run result fetched via evolvepro.run_result RPC after stage==="done". Not persisted. */
  evolveProRunResult: EvolveProRunResultResponse | null;
  evolveProError: EvolveProErrorInfo | null;
  evolveProDetecting: boolean;
  evolveProRunning: boolean;
  evolveProCancelling: boolean;
  evolveProRunStartedAt: number | null;
  esm2RecommendationLoading: boolean;
  esm2Downloads: Record<string, Esm2DownloadState>;
  esm2Installed: Record<string, boolean>;
  activeEsm2ModelId: string | null;
  embeddingCacheStatus: EvolveProEmbeddingCacheStatusResponse | null;
  embeddingCacheLoading: boolean;
  // Form input fields (persisted across tab unmount and refresh)
  evolveProRoundFiles: string[];
  evolveProWtFasta: string;
  evolveProWtSequence: string;
  evolveProOutputDir: string;
  evolveProTopN: number;

  detectEvolveProEnv: () => Promise<void>;
  loadEsm2Recommendation: () => Promise<void>;
  startEvolveProRun: (req: EvolveProRunRequest) => Promise<void>;
  cancelEvolveProRun: () => Promise<void>;
  setProgress: (p: EvolveProRunProgress) => void;
  loadRunResult: (outputDir: string) => Promise<void>;
  reset: () => void;
  startEsm2Download: (model: Esm2ModelRecommendation) => Promise<void>;
  cancelEsm2Download: (modelId: string) => Promise<void>;
  applyEsm2Progress: (p: Esm2DownloadProgress) => void;
  refreshEsm2Installed: () => Promise<void>;
  setActiveEsm2: (modelId: string | null) => void;
  resolveActiveEsm2: () => string | null;
  loadEmbeddingCacheStatus: (wtSequence: string, modelId: string) => Promise<void>;
  setEvolveProRoundFiles: (v: string[]) => void;
  setEvolveProWtFasta: (v: string) => void;
  setEvolveProWtSequence: (v: string) => void;
  setEvolveProOutputDir: (v: string) => void;
  setEvolveProTopN: (v: number) => void;
}

export const useEvolveProStore = create<EvolveProState>()(
  persist(
    (set, get) => ({
      evolveProEnvStatus: null,
      evolveProRunId: null,
      esm2Recommendation: null,
      evolveProProgress: null,
      evolveProResult: null,
      evolveProRunResult: null,
      evolveProError: null,
      evolveProDetecting: false,
      evolveProRunning: false,
      evolveProCancelling: false,
      evolveProRunStartedAt: null,
      esm2RecommendationLoading: false,
      esm2Downloads: {},
      esm2Installed: {},
      activeEsm2ModelId: null,
      embeddingCacheStatus: null,
      embeddingCacheLoading: false,
      evolveProRoundFiles: [],
      evolveProWtFasta: "",
      evolveProWtSequence: "",
      evolveProOutputDir: "",
      evolveProTopN: 0,

      detectEvolveProEnv: async () => {
        set({ evolveProDetecting: true, evolveProError: null });
        try {
          const status = await detectEvolveProEnv();
          set({ evolveProEnvStatus: status, evolveProDetecting: false });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set({
            evolveProDetecting: false,
            evolveProError: { kind: classifyError(message), message },
          });
        }
      },

      loadEsm2Recommendation: async () => {
        set({ esm2RecommendationLoading: true, evolveProError: null });
        try {
          const recommendation = await recommendEsm2Model();
          set({ esm2Recommendation: recommendation, esm2RecommendationLoading: false });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set({
            esm2RecommendationLoading: false,
            evolveProError: { kind: classifyError(message), message },
          });
        }
      },

      startEvolveProRun: async (request) => {
        const resolvedModelId = request.esm2_model_id || get().resolveActiveEsm2();
        if (!resolvedModelId) {
          set({
            evolveProError: {
              kind: "unknown",
              message: "ESM2 model not selected. Download a model first.",
            },
          });
          return;
        }
        const finalRequest: EvolveProRunRequest = {
          ...request,
          esm2_model_id: resolvedModelId,
        };
        set({
          evolveProRunning: true,
          evolveProCancelling: false,
          evolveProError: null,
          evolveProResult: null,
          evolveProProgress: null,
          evolveProRunId: null,
          evolveProRunStartedAt: Date.now(),
        });
        try {
          const resp = await startEvolveProRun(finalRequest);
          set({ evolveProRunId: resp.run_id });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set({
            evolveProRunning: false,
            evolveProError: { kind: classifyError(message), message },
          });
        }
      },

      cancelEvolveProRun: async () => {
        const runId = get().evolveProRunId;
        if (runId === null) return;
        set({ evolveProCancelling: true });
        try {
          await cancelEvolveProRun(runId);
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set({ evolveProError: { kind: classifyError(message), message } });
        } finally {
          set({ evolveProRunning: false });
        }
      },

      setProgress: (p) => {
        set({ evolveProProgress: p });
        if (p.stage === "done") {
          set({
            evolveProRunning: false,
            evolveProRunStartedAt: null,
            evolveProResult: p.result ?? null,
          });
          const outputDir = get().evolveProOutputDir;
          if (outputDir) {
            void get().loadRunResult(outputDir);
          }
        } else if (p.stage === "error") {
          const wasCancelling = get().evolveProCancelling;
          if (wasCancelling || isCancelExit(p.message)) {
            set({
              evolveProRunning: false,
              evolveProCancelling: false,
              evolveProRunStartedAt: null,
              evolveProError: { kind: "cancelled", message: "" },
            });
          } else {
            set({
              evolveProRunning: false,
              evolveProRunStartedAt: null,
              evolveProError: { kind: classifyError(p.message), message: p.message },
            });
          }
        }
      },

      loadRunResult: async (outputDir) => {
        try {
          const runResult = await getRunResult(outputDir);
          set({ evolveProRunResult: runResult });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set({ evolveProError: { kind: classifyError(message), message } });
        }
      },

      reset: () => {
        set({
          evolveProEnvStatus: null,
          evolveProRunId: null,
          esm2Recommendation: null,
          evolveProProgress: null,
          evolveProResult: null,
          evolveProRunResult: null,
          evolveProError: null,
          evolveProDetecting: false,
          evolveProRunning: false,
          evolveProCancelling: false,
          evolveProRunStartedAt: null,
          esm2RecommendationLoading: false,
          esm2Downloads: {},
          esm2Installed: {},
          activeEsm2ModelId: null,
          embeddingCacheStatus: null,
          embeddingCacheLoading: false,
          evolveProRoundFiles: [],
          evolveProWtFasta: "",
          evolveProWtSequence: "",
          evolveProOutputDir: "",
          evolveProTopN: 0,
        });
      },

      startEsm2Download: async (model) => {
        set((state) => ({
          esm2Downloads: {
            ...state.esm2Downloads,
            [model.model_id]: { status: "downloading", bytes: 0, total: model.expected_bytes },
          },
        }));
        try {
          const expectedBytes = model.expected_bytes > 0 ? model.expected_bytes : null;
          await esm2DownloadStart(model.model_id, model.download_url, expectedBytes);
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set((state) => ({
            esm2Downloads: {
              ...state.esm2Downloads,
              [model.model_id]: {
                status: "error",
                bytes: state.esm2Downloads[model.model_id]?.bytes ?? 0,
                total: model.expected_bytes,
                error: message,
              },
            },
          }));
        }
      },

      cancelEsm2Download: async (modelId) => {
        try {
          await esm2DownloadCancel(modelId);
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set((state) => ({
            esm2Downloads: {
              ...state.esm2Downloads,
              [modelId]: {
                ...state.esm2Downloads[modelId],
                status: "error",
                error: message,
              },
            },
          }));
        }
      },

      applyEsm2Progress: (p) => {
        set((state) => {
          const prev = state.esm2Downloads[p.model_id];
          const updated: Esm2DownloadState = {
            status: p.status,
            bytes: p.bytes,
            total: p.total,
            error: p.error ?? prev?.error,
          };
          const installedPatch =
            p.status === "done" ? { [p.model_id]: true } : {};
          return {
            esm2Downloads: { ...state.esm2Downloads, [p.model_id]: updated },
            esm2Installed: { ...state.esm2Installed, ...installedPatch },
          };
        });
        if (p.status === "done" && get().activeEsm2ModelId === null) {
          get().resolveActiveEsm2();
        }
      },

      refreshEsm2Installed: async () => {
        const models = get().esm2Recommendation?.models ?? [];
        if (models.length === 0) return;
        const results = await Promise.allSettled(
          models.map((m) => esm2CheckInstalled(m.model_id, m.expected_bytes)),
        );
        const patch: Record<string, boolean> = {};
        models.forEach((m, i) => {
          const r = results[i];
          if (r.status === "fulfilled") patch[m.model_id] = r.value;
        });
        set((state) => ({ esm2Installed: { ...state.esm2Installed, ...patch } }));
      },

      setActiveEsm2: (modelId) => {
        set({ activeEsm2ModelId: modelId });
      },

      setEvolveProRoundFiles: (v) => set({ evolveProRoundFiles: v }),
      setEvolveProWtFasta: (v) => set({ evolveProWtFasta: v }),
      setEvolveProWtSequence: (v) => set({ evolveProWtSequence: v }),
      setEvolveProOutputDir: (v) => set({ evolveProOutputDir: v }),
      setEvolveProTopN: (v) => set({ evolveProTopN: v }),

      loadEmbeddingCacheStatus: async (wtSequence, modelId) => {
        if (!wtSequence || !modelId) {
          set({ embeddingCacheStatus: null, embeddingCacheLoading: false });
          return;
        }
        set({ embeddingCacheLoading: true });
        try {
          const status = await getEmbeddingCacheStatus(wtSequence, modelId);
          set({ embeddingCacheStatus: status, embeddingCacheLoading: false });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          set({
            embeddingCacheStatus: null,
            embeddingCacheLoading: false,
            evolveProError: { kind: classifyError(message), message },
          });
        }
      },

      resolveActiveEsm2: () => {
        const { activeEsm2ModelId, esm2Installed, esm2Recommendation } = get();
        const models = esm2Recommendation?.models ?? [];

        if (activeEsm2ModelId !== null && esm2Installed[activeEsm2ModelId] === true) {
          return activeEsm2ModelId;
        }

        const PREFERRED = "esm2_t33_650M_UR50D";
        const preferredMeta = models.find((m) => m.model_id === PREFERRED);
        if (esm2Installed[PREFERRED] === true && preferredMeta?.status !== "blocked") {
          set({ activeEsm2ModelId: PREFERRED });
          return PREFERRED;
        }

        for (let i = SIZE_ORDER.length - 1; i >= 0; i--) {
          const id = SIZE_ORDER[i];
          const meta = models.find((m) => m.model_id === id);
          if (esm2Installed[id] === true && meta?.status !== "blocked") {
            set({ activeEsm2ModelId: id });
            return id;
          }
        }

        for (const id of SIZE_ORDER) {
          if (esm2Installed[id] === true) {
            set({ activeEsm2ModelId: id });
            return id;
          }
        }

        return null;
      },
    }),
    {
      name: "evolvepro-store",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        activeEsm2ModelId: state.activeEsm2ModelId,
        evolveProRoundFiles: state.evolveProRoundFiles,
        evolveProWtFasta: state.evolveProWtFasta,
        evolveProWtSequence: state.evolveProWtSequence,
        evolveProOutputDir: state.evolveProOutputDir,
        evolveProTopN: state.evolveProTopN,
      }),
    }
  )
);

// Global progress handler registration (module singleton).
// Registered once at module load time so progress updates reach the store
// regardless of which component tab is currently mounted.
setProgressHandler((p) => useEvolveProStore.getState().setProgress(p));
