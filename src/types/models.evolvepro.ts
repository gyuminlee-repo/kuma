/**
 * EVOLVEpro hand-written TS types for the third tool tab.
 *
 * Mirrors python-core/sidecar_evolvepro/models.py for the sidecar RPC payloads,
 * plus Rust-side / Tauri-event types that are NOT Pydantic models (download
 * progress, conda install progress, progress snapshots). The generated
 * counterpart (src/types/models.evolvepro.generated.ts) covers only the
 * Pydantic subset and is checked for drift by `pnpm gen:models:check`.
 *
 * Component code imports from this file. Naming bridges the Pydantic
 * `*Response` suffix to the shorter UI names (CondaStatus / EnvStatus /
 * CondaVerifyResult).
 */

export interface EvolveProDetectResponse {
  env_found: boolean;
  env_path: string | null;
  evolvepro_version: string | null;
  weights_cached: boolean;
  weights_path: string | null;
  cached_models?: Record<string, string>;
}

export interface EvolveProRunRequest {
  input_csv: string;
  round_files: string[];
  wt_sequence: string;
  wt_fasta?: string;
  n_rounds: number;
  output_dir: string;
  top_n: number;
  env_name: string;
  esm2_model_id: string;
}

export interface EvolveProRunStartResponse {
  run_id: string;
}

export interface EvolveProRunProgress {
  run_id: string;
  stage: "detect" | "loading" | "scoring" | "selecting" | "done" | "error";
  current: number;
  total: number;
  message: string;
}

/**
 * Snapshot returned by Rust ProgressCache via `get_run_progress` /
 * `list_active_runs`. Not a Pydantic model; mirrors the Rust struct.
 */
export interface EvolveProProgressSnapshot {
  run_id: string;
  stage: string;
  current: number;
  total: number;
  message: string;
  updated_at_ms: number;
}

export interface EvolveProRunResult {
  run_id: string;
  output_csv: string;
  top_variants: string[];
  elapsed_sec: number;
}

export interface EvolveProCancelRequest {
  run_id: string;
}

export interface Esm2ModelRecommendation {
  model_id: string;
  label: string;
  size_label: string;
  min_ram_gb: number;
  recommended_ram_gb: number;
  status: "safe" | "caution" | "blocked" | "unknown";
  reason: string;
  download_url: string;
  expected_bytes: number;
  installed: boolean;
}

/** Tauri-event payload (esm2://download-progress). Not a Pydantic model. */
export interface Esm2DownloadProgress {
  model_id: string;
  bytes: number;
  total: number;
  status: "downloading" | "done" | "cancelled" | "error";
  error?: string | null;
}

export interface Esm2RecommendationResponse {
  os: string;
  arch: string;
  ram_gb: number | null;
  disk_free_gb: number | null;
  recommended_model_id: string | null;
  recommended_label: string | null;
  models: Esm2ModelRecommendation[];
  warnings: string[];
}

export interface CondaStatus {
  installed: boolean;
  conda_exe: string | null;
  version: string | null;
}

export interface EnvStatus {
  exists: boolean;
  env_path: string | null;
  packages: Record<string, string | null>;
}

export interface CondaVerifyResult {
  ok: boolean;
  error: string | null;
}

/** Tauri-event payload (conda://install-progress). Not a Pydantic model. */
export interface CondaInstallProgress {
  status: "downloading" | "installing" | "done" | "cancelled" | "error" | "prefix_conflict";
  bytes?: number;
  total?: number;
  line?: string;
  conda_exe?: string;
  error?: string | null;
}

export interface CondaCreateEnvProgress {
  stage: "conda_create" | "pip_install" | "done" | "error";
  line?: string;
  current_package?: string;
  error?: string;
}

export interface CondaCreateEnvParams {
  env_name: string;
  conda_exe: string;
  python_version?: string;
}
