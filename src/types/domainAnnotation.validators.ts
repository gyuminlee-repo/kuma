import type { DomainAnnotationAttempt, DomainAnnotationBinding, DomainAnnotationJob, DomainAnnotationResult, DomainRuntimeStatus } from "./domainAnnotation";

const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const hash = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const integer = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v);
const fraction = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1;

export function isDomainAnnotationBinding(v: unknown): v is DomainAnnotationBinding {
  return record(v) && hash(v.bundle_sha256) && hash(v.source_sha256) && hash(v.reference_sha256)
    && typeof v.model_id === "string" && v.model_id.length > 0 && typeof v.chain_id === "string";
}

export function isDomainRuntimeStatus(v: unknown): v is DomainRuntimeStatus {
  return record(v) && ["installed", "missing", "corrupt", "licensing_blocked", "unsupported_platform"].includes(String(v.state))
    && v.engine === "merizo" && typeof v.platform === "string" && typeof v.message === "string"
    && (v.version === null || typeof v.version === "string")
    && typeof v.install_available === "boolean" && (v.available_version === null || typeof v.available_version === "string")
    && (!v.install_available || typeof v.available_version === "string")
    && (!(v.state === "licensing_blocked" || v.state === "unsupported_platform") || !v.install_available);
}

export function isDomainAnnotationJob(v: unknown): v is DomainAnnotationJob {
  return record(v) && typeof v.job_id === "string" && v.job_id.length > 0
    && ["queued", "running", "cancelling", "succeeded", "failed", "cancelled"].includes(String(v.state))
    && typeof v.message === "string" && isDomainAnnotationBinding(v.binding);
}

export function isDomainAnnotationResult(v: unknown): v is DomainAnnotationResult {
  if (!record(v) || !isDomainAnnotationBinding(v.binding) || !hash(v.binding_sha256)
    || !(v.job_id === null || typeof v.job_id === "string" && v.job_id.length > 0)
    || !(v.provenance === "managed" && typeof v.job_id === "string" || v.provenance === "imported" && v.job_id === null)
    || typeof v.provenance_note !== "string" || v.engine !== "merizo" || v.coordinate_frame !== "reference"
    || !integer(v.total_residues) || v.total_residues < 1 || v.total_residues > 10000
    || !integer(v.assigned_residues) || v.assigned_residues < 1 || v.assigned_residues > v.total_residues
    || !fraction(v.coverage) || !fraction(v.confidence)
    || !Array.isArray(v.domains) || v.domains.length === 0 || v.domains.length > v.total_residues
    || !Array.isArray(v.unassigned_positions)) return false;
  const total = v.total_residues;
  const used = new Set<number>();
  const positions = (values: unknown): values is number[] => Array.isArray(values) && values.length <= total
    && values.every((p, i) => integer(p) && p >= 1 && p <= total && (i === 0 || p > values[i - 1]));
  for (const domain of v.domains) {
    if (!record(domain) || !positions(domain.positions) || !domain.positions.length
      || !Array.isArray(domain.segments) || !domain.segments.length || domain.segments.length > domain.positions.length) return false;
    const expanded: number[] = [];
    for (const segment of domain.segments) {
      if (!record(segment) || !integer(segment.start) || !integer(segment.end)
        || segment.start < 1 || segment.end > total || segment.end < segment.start
        || expanded.length > 0 && segment.start <= expanded[expanded.length - 1] + 1) return false;
      for (let p = segment.start; p <= segment.end; p++) expanded.push(p);
    }
    const domainPositions = domain.positions;
    if (expanded.length !== domainPositions.length || expanded.some((p, i) => p !== domainPositions[i])) return false;
    for (const p of domain.positions) { if (used.has(p)) return false; used.add(p); }
  }
  if (used.size !== v.assigned_residues || v.coverage !== used.size / total || !positions(v.unassigned_positions)) return false;
  const missing = Array.from({ length: total }, (_, i) => i + 1).filter((p) => !used.has(p));
  const unassigned = v.unassigned_positions;
  return missing.length === unassigned.length && missing.every((p, i) => p === unassigned[i]);
}

export function isDomainAnnotationAttempt(v: unknown): v is DomainAnnotationAttempt {
  return record(v) && typeof v.attempt_id === "string" && /^[a-f0-9]{32}$/.test(v.attempt_id)
    && ["unknown", "pending", "job", "cancelled", "failed", "expired"].includes(String(v.state))
    && typeof v.message === "string"
    && (v.state === "job" ? isDomainAnnotationJob(v.job) : v.job === null);
}
