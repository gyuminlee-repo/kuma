/** Optional structural annotation only. Never part of selection or design inputs. */
export interface DomainAnnotationSource {
  prediction_bundle_path: string;
  prediction_bundle_sha256: string;
  prediction_model_id: string;
  prediction_chain_id: string;
  ref_seq: string;
}

export interface DomainRuntimeStatus {
  state: "installed" | "missing" | "corrupt" | "licensing_blocked" | "unsupported_platform";
  engine: "merizo";
  platform: string;
  version: string | null;
  message: string;
  install_available: boolean;
  available_version: string | null;
}

export interface DomainAnnotationBinding {
  bundle_sha256: string;
  source_sha256: string;
  reference_sha256: string;
  model_id: string;
  chain_id: string;
}

export interface DomainAnnotationJob {
  job_id: string;
  state: "queued" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
  message: string;
  binding: DomainAnnotationBinding;
}

export interface DomainAnnotationResult {
  job_id: string | null;
  binding: DomainAnnotationBinding;
  binding_sha256: string;
  provenance: "managed" | "imported";
  provenance_note: string;
  engine: "merizo";
  coordinate_frame: "reference";
  domains: Array<{ segments: Array<{ start: number; end: number }>; positions: number[] }>;
  unassigned_positions: number[];
  assigned_residues: number;
  total_residues: number;
  coverage: number;
  confidence: number;
}

/** Exact client-attempt recovery prevents late dispatch after cancellation. */
export interface DomainAnnotationAttempt {
  attempt_id: string;
  state: "unknown" | "pending" | "job" | "cancelled" | "failed" | "expired";
  message: string;
  job: DomainAnnotationJob | null;
}
