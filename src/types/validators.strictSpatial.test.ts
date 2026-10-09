import { describe, expect, it } from "vitest";
import { strictSpatialFixture } from "@/test-utils/strictSpatialFixture";
import { getRpcResultValidator } from "./validators";

describe("strict spatial response contract", () => {
  const result = () => ({ variants: ["A2G", "A4V"], y_preds: [2, 1], selected_count: 2, total_count: 4, strict_spatial: strictSpatialFixture() });
  const valid = getRpcResultValidator("load_evolvepro_csv");
  it("accepts legacy responses and complete certificates", () => {
    expect(valid(result())).toBe(true);
    expect(valid({ ...result(), strict_spatial: undefined })).toBe(true);
  });
  it.each([{}, { schema_version: 2 }, { mapping: [{ reference_position: 2, coordinate: [1, 2, Number.NaN] }] }, { candidate_sha256: null }])("rejects malformed certificates: %j", (patch) => {
    const value = result();
    expect(valid({ ...value, strict_spatial: Object.keys(patch).length ? { ...value.strict_spatial, ...patch } : patch })).toBe(false);
  });
  it("preserves source features with uncertain ranges and raw evidence", () => {
    const features = [{ type: "Binding site", ligand: { name: "Metal" }, evidences: [{ evidenceCode: "ECO:0000269" }], location: { start: { modifier: "UNCERTAIN" } } }];
    const value = { accession: "P12345", source: "uniprot", has_annotation: true, active_site_positions: [], binding_positions: [], features, annotation_status: "present", sequence_version: 2 };
    expect(getRpcResultValidator("fetch_active_site_residues")(value)).toBe(true);
    expect(value.features).toBe(features);
  });
});
