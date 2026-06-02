/**
 * EVOLVEpro IPC client (third tool tab).
 *
 * Adapted from evolvepro-gui/src/lib/ipc.ts to kuma's multi-sidecar bridge:
 * sidecar RPC goes through `rpc("evolvepro", method, params)` (kuma routes on
 * `kind`), while Rust-direct Tauri commands (get_run_progress, esm2_*, pty_*,
 * conda_install_*, read_text_head, probe_writable_dir) keep their kind-less
 * `invoke(...)` calls. The shared `sidecar://progress` channel is filtered to
 * `kind === "evolvepro"` so kuro/mame events do not leak in.
 */
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { killSidecar as killSidecarRpc, rpc as kumaRpc } from "../ipc";
import type {
  CondaCreateEnvParams,
  CondaInstallProgress,
  CondaStatus,
  CondaVerifyResult,
  EnvStatus,
  Esm2DownloadProgress,
  Esm2RecommendationResponse,
  EvolveProCancelRequest,
  EvolveProDetectResponse,
  EvolveProEmbeddingCacheStatusResponse,
  EvolveProProgressSnapshot,
  EvolveProRunProgress,
  EvolveProRunResult,
  EvolveProRunRequest,
  EvolveProRunResultResponse,
  EvolveProRunStartResponse,
} from "@/types/models.evolvepro";

/** Sidecar RPC against the evolvepro sidecar. */
export async function rpc<T = unknown>(method: string, params: unknown = {}): Promise<T> {
  return kumaRpc<T>("evolvepro", method, params);
}

export async function ping(): Promise<{ ok: boolean }> {
  return rpc<{ ok: boolean }>("ping", {});
}

export async function killSidecar(): Promise<void> {
  await killSidecarRpc("evolvepro");
}

export async function detectEvolveProEnv(): Promise<EvolveProDetectResponse> {
  return rpc<EvolveProDetectResponse>("evolvepro.detect", {});
}

export async function recommendEsm2Model(): Promise<Esm2RecommendationResponse> {
  return rpc<Esm2RecommendationResponse>("esm2.recommend", {});
}

export async function getEmbeddingCacheStatus(
  wtSequence: string,
  esm2ModelId: string,
): Promise<EvolveProEmbeddingCacheStatusResponse> {
  return rpc<EvolveProEmbeddingCacheStatusResponse>("evolvepro.embedding_cache_status", {
    wt_sequence: wtSequence,
    esm2_model_id: esm2ModelId,
  });
}

export async function startEvolveProRun(
  req: EvolveProRunRequest,
): Promise<EvolveProRunStartResponse> {
  return rpc<EvolveProRunStartResponse>("evolvepro.run", req);
}

export async function cancelEvolveProRun(
  runId: string,
): Promise<{ ok: boolean; reason?: string }> {
  const req: EvolveProCancelRequest = { run_id: runId };
  return rpc<{ ok: boolean; reason?: string }>("evolvepro.cancel", req);
}

export async function getRunResult(outputDir: string): Promise<EvolveProRunResultResponse> {
  return rpc<EvolveProRunResultResponse>("evolvepro.run_result", { output_dir: outputDir });
}

let progressUnlisten: UnlistenFn | null = null;
let progressListenerPromise: Promise<UnlistenFn> | null = null;
let onProgress: ((p: EvolveProRunProgress) => void) | null = null;

interface ProgressEventPayload {
  kind?: "kuro" | "mame" | "evolvepro";
  method?: string;
  params?: {
    type?: string;
    run_id?: string;
    stage?: string;
    current?: number;
    total?: number;
    message?: string;
    current_package?: string | null;
    indeterminate?: boolean;
    result?: EvolveProRunResult;
  };
}

export interface CondaCreateProgressData {
  stage: "conda_create" | "pip_install" | "pip_install_progress";
  current: number;
  total: number;
  message: string;
  current_package: string | null;
  indeterminate: boolean;
}

let onCondaCreate: ((line: string) => void) | null = null;
let onCondaCreateComplete: ((ok: boolean, error?: string) => void) | null = null;
let onCondaCreateProgress: ((data: CondaCreateProgressData) => void) | null = null;

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export function setCondaCreateProgressDataHandler(
  handler: ((data: CondaCreateProgressData) => void) | null,
): void {
  onCondaCreateProgress = handler;
  if (handler) void ensureProgressListener();
}

export function setCondaCreateProgressHandler(
  handler: ((line: string) => void) | null,
): void {
  onCondaCreate = handler;
  if (handler) void ensureProgressListener();
}

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function prepareCondaCreateProgressListener(): Promise<void> {
  await ensureProgressListener();
}

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export function setCondaCreateCompleteHandler(
  handler: ((ok: boolean, error?: string) => void) | null,
): void {
  onCondaCreateComplete = handler;
  if (handler) void ensureProgressListener();
}

async function ensureProgressListener(): Promise<void> {
  if (progressUnlisten) return;
  if (!progressListenerPromise) {
    progressListenerPromise = listen<ProgressEventPayload>(
      "sidecar://progress",
      (event) => {
        // Shared channel: kuro/mame events also arrive here. Ignore non-evolvepro.
        if (event.payload?.kind !== "evolvepro") return;
        const params = event.payload?.params;
        if (!params) return;

        if (params.run_id === "conda_create") {
          const stage = params.stage ?? "";
          if (stage === "complete") {
            if (onCondaCreateComplete) onCondaCreateComplete(true);
            return;
          }
          if (stage === "create_error") {
            const errMsg = params.message ?? "conda create_env failed";
            if (onCondaCreateComplete) onCondaCreateComplete(false, errMsg);
            return;
          }
          if (stage === "cancelled") {
            const line = params.message ?? "cancelled";
            if (onCondaCreate) onCondaCreate(`[cancelled] ${line}`);
            if (onCondaCreateComplete) onCondaCreateComplete(false, "__cancelled__");
            return;
          }
          if (
            stage === "conda_create" ||
            stage === "pip_install" ||
            stage === "pip_install_progress"
          ) {
            if (onCondaCreateProgress) {
              onCondaCreateProgress({
                stage: stage as CondaCreateProgressData["stage"],
                current: params.current ?? 0,
                total: params.total ?? 0,
                message: params.message ?? "",
                current_package: params.current_package ?? null,
                indeterminate: params.indeterminate ?? false,
              });
            }
          }
          const line = params.message ?? "";
          if (line && onCondaCreate) onCondaCreate(line);
          return;
        }

        if (params.type === "evolvepro_progress" && onProgress) {
          onProgress({
            run_id: params.run_id ?? "",
            stage: (params.stage ?? "loading") as EvolveProRunProgress["stage"],
            current: params.current ?? 0,
            total: params.total ?? 0,
            message: params.message ?? "",
            result: params.result,
          });
        }
      },
    );
  }
  progressUnlisten = await progressListenerPromise;
}

export function setProgressHandler(
  handler: ((p: EvolveProRunProgress) => void) | null,
): void {
  onProgress = handler;
  if (handler) void ensureProgressListener();
}

/**
 * Query Rust ProgressCache for the latest snapshot of a specific run.
 * Returns null when the run is unknown (cache cleared on app restart).
 */
export async function getRunProgress(
  runId: string,
): Promise<EvolveProProgressSnapshot | null> {
  const snap = await invoke<EvolveProProgressSnapshot | null>("get_run_progress", { runId });
  return snap ?? null;
}

/** List all cached run snapshots. Used on mount to recover UI after webview reload. */
export async function listActiveRuns(): Promise<EvolveProProgressSnapshot[]> {
  return invoke<EvolveProProgressSnapshot[]>("list_active_runs");
}

export async function esm2CacheDir(): Promise<string> {
  return invoke<string>("esm2_cache_dir");
}

export async function esm2CheckInstalled(
  modelId: string,
  expectedMinBytes: number,
): Promise<boolean> {
  return invoke<boolean>("esm2_check_installed", { modelId, expectedMinBytes });
}

export type Esm2DiagnoseEntry = { path: string; exists: boolean; size: number };

export async function esm2Diagnose(modelId: string): Promise<Esm2DiagnoseEntry[]> {
  return invoke<Esm2DiagnoseEntry[]>("esm2_diagnose", { modelId });
}

export async function esm2DownloadStart(
  modelId: string,
  url: string,
  expectedBytes: number | null,
): Promise<void> {
  return invoke<void>("esm2_download_start", { modelId, url, expectedBytes });
}

export async function esm2DownloadCancel(modelId: string): Promise<void> {
  return invoke<void>("esm2_download_cancel", { modelId });
}

let esm2ProgressUnlisten: UnlistenFn | null = null;
let esm2ProgressListenerPromise: Promise<UnlistenFn> | null = null;
let onEsm2Progress: ((p: Esm2DownloadProgress) => void) | null = null;

export async function subscribeEsm2DownloadProgress(
  cb: (p: Esm2DownloadProgress) => void,
): Promise<UnlistenFn> {
  onEsm2Progress = cb;
  if (esm2ProgressUnlisten) return esm2ProgressUnlisten;
  if (!esm2ProgressListenerPromise) {
    esm2ProgressListenerPromise = listen<Esm2DownloadProgress>("esm2://download-progress", (event) => {
      if (onEsm2Progress) onEsm2Progress(event.payload);
    });
  }
  esm2ProgressUnlisten = await esm2ProgressListenerPromise;
  return esm2ProgressUnlisten;
}

export async function unsubscribeEsm2DownloadProgress(): Promise<void> {
  if (esm2ProgressUnlisten) {
    esm2ProgressUnlisten();
    esm2ProgressUnlisten = null;
    esm2ProgressListenerPromise = null;
    onEsm2Progress = null;
  }
}

// Sidecar RPC: conda.* methods
export async function condaDetect(): Promise<CondaStatus> {
  return rpc<CondaStatus>("conda.detect", {});
}

export async function condaDetectEnv(envName: string = "evolvepro"): Promise<EnvStatus> {
  return rpc<EnvStatus>("conda.detect_env", { env_name: envName });
}

export async function condaVerifyEnv(envName: string, condaExe: string): Promise<CondaVerifyResult> {
  return rpc<CondaVerifyResult>("conda.verify_env", { env_name: envName, conda_exe: condaExe });
}

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function condaCreateEnv(params: CondaCreateEnvParams): Promise<{ ok: boolean }> {
  return rpc<{ ok: boolean }>("conda.create_env", params);
}

export async function condaDeleteEnv(envName: string, condaExe: string): Promise<{ ok: boolean }> {
  return rpc<{ ok: boolean }>("conda.delete_env", { env_name: envName, conda_exe: condaExe });
}

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function condaCancelCreateEnv(
  envName: string = "evolvepro",
  condaExe: string = "",
): Promise<{ cancelled: boolean; reason?: string }> {
  return rpc<{ cancelled: boolean; reason?: string }>("conda.cancel_create_env", {
    env_name: envName,
    conda_exe: condaExe,
  });
}

export type CondaInitShellResult = { ok: boolean; shell: string; output: string; error: string | null };

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function condaInitShell(condaExe: string, shell?: string): Promise<CondaInitShellResult> {
  return rpc<CondaInitShellResult>("conda.init_shell", { conda_exe: condaExe, shell });
}

// Tauri direct commands: miniforge installer (Rust side)
/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function condaInstallMiniforge(): Promise<void> {
  return invoke<void>("conda_install_miniforge");
}

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function condaInstallCancel(): Promise<void> {
  return invoke<void>("conda_install_cancel");
}

export async function condaInstallRemovePrefix(): Promise<void> {
  return invoke<void>("conda_install_remove_prefix");
}

// Progress listener for miniforge download/install (Tauri event channel)
let condaInstallUnlisten: UnlistenFn | null = null;
let condaInstallListenerPromise: Promise<UnlistenFn> | null = null;
let onCondaInstall: ((p: CondaInstallProgress) => void) | null = null;

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function subscribeCondaInstallProgress(
  cb: (p: CondaInstallProgress) => void,
): Promise<UnlistenFn> {
  onCondaInstall = cb;
  if (condaInstallUnlisten) return condaInstallUnlisten;
  if (!condaInstallListenerPromise) {
    condaInstallListenerPromise = listen<CondaInstallProgress>("conda://install-progress", (event) => {
      if (onCondaInstall) onCondaInstall(event.payload);
    });
  }
  condaInstallUnlisten = await condaInstallListenerPromise;
  return condaInstallUnlisten;
}

/** @deprecated Superseded by PTY runCommand flow in CondaSetupWizard. */
export async function unsubscribeCondaInstallProgress(): Promise<void> {
  if (condaInstallUnlisten) {
    condaInstallUnlisten();
    condaInstallUnlisten = null;
    condaInstallListenerPromise = null;
    onCondaInstall = null;
  }
}

// ---------------------------------------------------------------------------
// PTY bindings (xterm.js embedded terminal)
// ---------------------------------------------------------------------------

export type PtyOutputPayload = { session_id: number; data: string };

export async function ptySpawn(opts: { shell?: string; cwd?: string; cols: number; rows: number }): Promise<number> {
  return invoke<number>("pty_spawn", opts);
}

export async function ptyWrite(sessionId: number, data: string): Promise<void> {
  return invoke("pty_write", { sessionId, data });
}

export async function ptyResize(sessionId: number, cols: number, rows: number): Promise<void> {
  return invoke("pty_resize", { sessionId, cols, rows });
}

export async function ptyKill(sessionId: number): Promise<void> {
  return invoke("pty_kill", { sessionId });
}

export async function onPtyOutput(handler: (p: PtyOutputPayload) => void): Promise<UnlistenFn> {
  return listen<PtyOutputPayload>("pty://output", (e) => handler(e.payload));
}

// Validation helper Tauri commands (used by lib/evolveProValidation).
export async function readTextHead(path: string, maxBytes: number): Promise<string> {
  return invoke<string>("read_text_head", { path, maxBytes });
}

export async function probeWritableDir(path: string): Promise<void> {
  return invoke<void>("probe_writable_dir", { path });
}
