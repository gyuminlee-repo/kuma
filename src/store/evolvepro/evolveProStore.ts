import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  cancelEvolveProRun,
  detectEvolveProEnv,
  esm2CheckInstalled,
  esm2DownloadCancel,
  esm2DownloadStart,
  recommendEsm2Model,
  startEvolveProRun,
} from "@/lib/ipc-evolvepro";
import type {
  Esm2DownloadProgress,
  Esm2ModelRecommendation,
  Esm2RecommendationResponse,
  EvolveProDetectResponse,
  EvolveProRunProgress,
  EvolveProRunRequest,
  EvolveProRunResult,
} from "@/types/models.evolvepro";

export type EvolveProErrorKind =
  | "env_not_found"
  | "network"
  | "disk_full"
  | "permission"
  | "runtime_error"
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
  evolveProError: EvolveProErrorInfo | null;
  evolveProDetecting: boolean;
  evolveProRunning: boolean;
  esm2RecommendationLoading: boolean;
  esm2Downloads: Record<string, Esm2DownloadState>;
  esm2Installed: Record<string, boolean>;
  activeEsm2ModelId: string | null;

  detectEvolveProEnv: () => Promise<void>;
  loadEsm2Recommendation: () => Promise<void>;
  startEvolveProRun: (req: EvolveProRunRequest) => Promise<void>;
  cancelEvolveProRun: () => Promise<void>;
  setProgress: (p: EvolveProRunProgress) => void;
  reset: () => void;
  startEsm2Download: (model: Esm2ModelRecommendation) => Promise<void>;
  cancelEsm2Download: (modelId: string) => Promise<void>;
  applyEsm2Progress: (p: Esm2DownloadProgress) => void;
  refreshEsm2Installed: () => Promise<void>;
  setActiveEsm2: (modelId: string | null) => void;
  resolveActiveEsm2: () => string | null;
}

export const useEvolveProStore = create<EvolveProState>()(
  persist(
    (set, get) => ({
      evolveProEnvStatus: null,
      evolveProRunId: null,
      esm2Recommendation: null,
      evolveProProgress: null,
      evolveProResult: null,
      evolveProError: null,
      evolveProDetecting: false,
      evolveProRunning: false,
      esm2RecommendationLoading: false,
      esm2Downloads: {},
      esm2Installed: {},
      activeEsm2ModelId: null,

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
          evolveProError: null,
          evolveProResult: null,
          evolveProProgress: null,
          evolveProRunId: null,
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
          set({ evolveProRunning: false });
        } else if (p.stage === "error") {
          set({
            evolveProRunning: false,
            evolveProError: { kind: classifyError(p.message), message: p.message },
          });
        }
      },

      reset: () => {
        set({
          evolveProEnvStatus: null,
          evolveProRunId: null,
          esm2Recommendation: null,
          evolveProProgress: null,
          evolveProResult: null,
          evolveProError: null,
          evolveProDetecting: false,
          evolveProRunning: false,
          esm2RecommendationLoading: false,
          esm2Downloads: {},
          esm2Installed: {},
          activeEsm2ModelId: null,
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
      partialize: (state) => ({ activeEsm2ModelId: state.activeEsm2ModelId }),
    }
  )
);
