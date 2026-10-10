import type { DomainAnnotationJob, DomainAnnotationResult, DomainRuntimeStatus } from "@/types/domainAnnotation";
import { predictionBundleInventory } from "./predictionBundleFixture";
export const domainBinding = { bundle_sha256: "d".repeat(64), source_sha256: "a".repeat(64),
  reference_sha256: "962aa3aaa69bde3cbbf6c6bd90a203585c65e5cefccdc0c28ce4d183e0cedc3f", model_id: "job_model_0.cif", chain_id: "A" };
export function domainRuntimeFixture(patch: Partial<DomainRuntimeStatus> = {}): DomainRuntimeStatus {
  return { state: "installed", engine: "merizo", platform: "test-platform", version: "test-version", message: "Verified test fixture",
    install_available: true, available_version: "test-version", ...patch };
}
export function domainJobFixture(state: DomainAnnotationJob["state"] = "queued"): DomainAnnotationJob {
  return { job_id: "1".repeat(32), state, message: state, binding: { ...domainBinding } };
}
export function domainResultFixture(provenance: "managed" | "imported" = "imported"): DomainAnnotationResult {
  return { job_id: provenance === "managed" ? "1".repeat(32) : null, binding: { ...domainBinding }, binding_sha256: "c".repeat(64),
    engine: "merizo", coordinate_frame: "reference", provenance, provenance_note: "Test-only consistency evidence",
    domains: [{ segments: [{ start: 1, end: 2 }, { start: 4, end: 4 }], positions: [1, 2, 4] }],
    unassigned_positions: [3, 5], assigned_residues: 3, total_residues: 5, coverage: 0.6, confidence: 0.9 };
}
export function colabFoldDomainInventory() { return { ...predictionBundleInventory(), format: "colabfold" as const }; }
export const domainReferenceFixture = { header: "reference", seq_length: 15, genes: [{ gene: "target", product: "target",
  cds_start: 1, cds_end: 15, aa_length: 5, translation: "MAAAA" }] };
