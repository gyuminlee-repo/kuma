import type { PredictionBundleEvidence, PredictionBundleInventory } from "@/types/models";
import { strictSpatialFixture } from "./strictSpatialFixture";

export function predictionBundleInventory(): PredictionBundleInventory {
  return { schema_version: 1, source_name: "saved-prediction.zip", bundle_sha256: "d".repeat(64),
    format: "af3_server", source_url: "https://alphafoldserver.com/", terms_url: "https://alphafoldserver.com/output-terms",
    recommended_model_id: "job_model_0.cif", recommendation_reason: "producer_rank",
    models: ["job_model_0.cif", "job_model_1.cif"].map((model_id, index) => ({ model_id, producer_rank: index + 1, structure_member: model_id,
      confidence_member: model_id.replace("model", "full_data").replace(".cif", ".json"), structure_format: "cif" as const,
      chains: [{ chain_id: "A", author_chain_id: "X", sequence: "MAAAA", length: 5 },
        { chain_id: "B", author_chain_id: "Y", sequence: "MAAAA", length: 5 }] })) };
}

export function predictionBundleEvidence(overrides: Partial<PredictionBundleEvidence> = {}): PredictionBundleEvidence {
  const inventory = predictionBundleInventory();
  const model = inventory.models[0];
  return { format: inventory.format, source_name: inventory.source_name, bundle_sha256: inventory.bundle_sha256,
    model_id: model.model_id, chain_id: "A", author_chain_id: "X", structure_member: model.structure_member,
    confidence_member: model.confidence_member, structure_sha256: "a".repeat(64), confidence_sha256: "e".repeat(64),
    source_url: inventory.source_url, terms_url: inventory.terms_url, display_sha256: "f".repeat(64),
    display_kind: "reference-ca-trace", plddt_by_reference: [90, 20, null, null, 80], plddt_source: "paired model confidence",
    pae: { status: "available", source: "paired confidence JSON", dimension: 5, mean: 7, max: 14,
      scope: "selected-chain-polymer", directional: true }, interdomain_confidence: "not_assessed", warnings: [], ...overrides };
}

export function importedSpatialFixture(overrides: Partial<PredictionBundleEvidence> = {}) {
  const report = strictSpatialFixture();
  return { ...report, source_accession: "local-prediction", structure_format: "pdb" as const,
    pdb_text: report.mapping.map((row, index) => `ATOM  ${String(index + 1).padStart(5)}  CA  ALA A${String(row.reference_position).padStart(4)}    ${row.coordinate.map((value) => value.toFixed(3).padStart(8)).join("")}  1.00  0.00           C`).join("\n") + "\nEND\n",
    prediction_bundle: predictionBundleEvidence(overrides),
    mapping: report.mapping.map((row) => ({ ...row, chain_id: "X", model_id: "1", polymer_position: row.reference_position,
      viewer_position: row.reference_position, viewer_chain_id: "A", viewer_insertion_code: "" })) };
}
