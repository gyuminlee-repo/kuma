import { describe, expect, it } from "vitest";
import {
  importedSpatialFixture,
  predictionBundleEvidence,
  predictionBundleInventory,
} from "@/test-utils/predictionBundleFixture";
import { getRpcResultValidator } from "./validators";

const inspect = getRpcResultValidator("inspect_prediction_bundle");
const load = getRpcResultValidator("load_evolvepro_csv");

function importedResponse(report: unknown = importedSpatialFixture()) {
  return {
    variants: ["A2G", "A4V"], y_preds: [2, 1], selected_count: 2, total_count: 3,
    strict_spatial: report,
  };
}

function evidenceResponse(patch: Record<string, unknown>) {
  const report = importedSpatialFixture();
  return importedResponse({ ...report, prediction_bundle: { ...report.prediction_bundle, ...patch } });
}

const malformedHashes = [null, "", "a".repeat(63), "a".repeat(65), "g".repeat(64), "A".repeat(64), 42];
const unsafeUrls = ["http://example.com/", "javascript:alert(1)", "data:text/html,test", "file:///tmp/test", "//example.com", "invalid-url"];
const sourceNotice = () => ({ member: "TERMS_OF_USE.md", sha256: "9".repeat(64), text: "Retain this source notice." });

describe("prediction bundle inspection RPC contract", () => {
  it.each(["af3_server", "colabfold"] as const)("accepts a complete %s inventory", (format) => {
    const inventory = { ...predictionBundleInventory(), format };
    expect(inspect(inventory)).toBe(true);
    expect(inventory.models).toHaveLength(2);
    expect(inventory.models[0].chains.map((chain) => chain.chain_id)).toEqual(["A", "B"]);
  });

  it("accepts a model with no confidence file and no terms URL", () => {
    const inventory = predictionBundleInventory();
    expect(inspect({ ...inventory, terms_url: null,
      models: inventory.models.map((model) => ({ ...model, confidence_member: null })) })).toBe(true);
  });

  it.each(malformedHashes)("rejects malformed bundle hashes: %j", (bundle_sha256) => {
    expect(inspect({ ...predictionBundleInventory(), bundle_sha256 })).toBe(false);
  });

  it.each([
    { schema_version: 2 }, { format: "unknown" }, { models: [] }, { models: null },
  ])("rejects malformed inventory fields: %j", (patch) => {
    expect(inspect({ ...predictionBundleInventory(), ...patch })).toBe(false);
  });

  it("rejects duplicate model IDs even when their chain inventories differ", () => {
    const inventory = predictionBundleInventory();
    const model = inventory.models[0];
    expect(inspect({ ...inventory, models: [model, { ...model, chains: [model.chains[1]] }] })).toBe(false);
  });

  it("rejects duplicate chain IDs within a model", () => {
    const inventory = predictionBundleInventory();
    const model = inventory.models[0];
    expect(inspect({ ...inventory, models: [{ ...model, chains: [model.chains[0],
      { ...model.chains[0], author_chain_id: "OTHER" }] }] })).toBe(false);
  });

  it.each([
    { model_id: "" }, { structure_member: "different-model.cif" },
    { structure_format: "xyz" }, { confidence_member: 42 }, { chains: [] },
  ])("rejects invalid model provenance: %j", (patch) => {
    const inventory = predictionBundleInventory();
    expect(inspect({ ...inventory, models: [{ ...inventory.models[0], ...patch }] })).toBe(false);
  });

  it.each([{ sequence: "" }, { sequence: "maaaa" }, { sequence: "MA-AA" }, { length: 6 }])(
    "rejects malformed chain sequences or lengths: %j", (patch) => {
      const inventory = predictionBundleInventory();
      const model = inventory.models[0];
      expect(inspect({ ...inventory, models: [{ ...model, chains: [{ ...model.chains[0], ...patch }] }] })).toBe(false);
    },
  );

  it.each(unsafeUrls)("rejects unsafe source and terms URLs: %s", (url) => {
    expect(inspect({ ...predictionBundleInventory(), source_url: url })).toBe(false);
    expect(inspect({ ...predictionBundleInventory(), terms_url: url })).toBe(false);
  });
});

describe("imported strict spatial evidence RPC contract", () => {
  it("accepts the imported certificate and retains original and viewer numbering separately", () => {
    const response = importedResponse();
    expect(load(response)).toBe(true);
    const report = importedSpatialFixture();
    expect(report.mapping[0]).toMatchObject({ structure_position: 12, chain_id: "X",
      reference_position: 2, viewer_position: 2, viewer_chain_id: "A", viewer_insertion_code: "" });
    expect(report.prediction_bundle).toEqual(predictionBundleEvidence());
  });

  it("preserves unavailable pLDDT values as null and accepts valid confidence endpoints", () => {
    const report = importedSpatialFixture({ plddt_by_reference: [0, 100, null, null, 80] });
    const confidence = report.prediction_bundle.plddt_by_reference;
    expect(load(importedResponse(report))).toBe(true);
    expect(report.prediction_bundle.plddt_by_reference).toBe(confidence);
    expect(confidence).toEqual([0, 100, null, null, 80]);
  });

  it.each([-0.01, 100.01, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, "90", undefined])(
    "rejects invalid confidence scores: %s", (score) => {
      expect(load(evidenceResponse({ plddt_by_reference: [90, score, null, null, 80] }))).toBe(false);
    },
  );

  it.each([{ plddt_by_reference: [] }, { plddt_by_reference: [90, 20, null, null] }])(
    "rejects confidence arrays that cannot cover the mapped reference: %j", ({ plddt_by_reference }) => {
    expect(load(evidenceResponse({ plddt_by_reference }))).toBe(false);
    },
  );

  it.each(["bundle_sha256", "structure_sha256", "confidence_sha256", "display_sha256", "sequence_sha256"])(
    "rejects malformed %s", (field) => {
      for (const hash of malformedHashes.filter((value) => value !== null)) {
        expect(load(evidenceResponse({ [field]: hash })), `${field}=${String(hash)}`).toBe(false);
      }
    },
  );

  it.each(unsafeUrls)("rejects unsafe evidence source and terms URLs: %s", (url) => {
    expect(load(evidenceResponse({ source_url: url }))).toBe(false);
    expect(load(evidenceResponse({ terms_url: url }))).toBe(false);
  });

  it("accepts unavailable PAE and absent paired confidence without manufacturing scores", () => {
    const report = importedSpatialFixture({ confidence_member: null, confidence_sha256: null,
      plddt_by_reference: [null, null, null, null, null], plddt_source: "unavailable",
      pae: { status: "unavailable", source: null, dimension: 0, mean: null, max: null,
        scope: "selected-chain-polymer", directional: true } });
    expect(load(importedResponse(report))).toBe(true);
    expect(report.prediction_bundle.pae.mean).toBeNull();
    expect(report.prediction_bundle.interdomain_confidence).toBe("not_assessed");
  });

  it("accepts available PAE with unknown aggregate values", () => {
    const evidence = predictionBundleEvidence();
    expect(load(evidenceResponse({ pae: { ...evidence.pae, mean: null, max: null } }))).toBe(true);
  });

  it.each([
    { status: "unknown" }, { dimension: -1 }, { dimension: 1.5 }, { dimension: 0 },
    { source: null }, { mean: -1 }, { mean: Number.NaN }, { max: Number.POSITIVE_INFINITY },
    { mean: 15, max: 14 }, { mean: null, max: 14 }, { mean: 7, max: null },
    { status: "unavailable", mean: 7, max: 14 }, { scope: "whole-complex" }, { directional: false },
  ])("rejects contradictory PAE summaries: %j", (patch) => {
    expect(load(evidenceResponse({ pae: { ...predictionBundleEvidence().pae, ...patch } }))).toBe(false);
  });

  it.each([
    { viewer_position: 12 }, { viewer_position: 0 }, { viewer_position: undefined },
    { viewer_chain_id: "X" }, { viewer_chain_id: undefined },
    { viewer_insertion_code: "B" }, { viewer_insertion_code: undefined },
  ])("rejects viewer coordinate overrides outside the reference CA trace: %j", (patch) => {
    const report = importedSpatialFixture();
    expect(load(importedResponse({ ...report,
      mapping: report.mapping.map((row, index) => index === 0 ? { ...row, ...patch } : row) }))).toBe(false);
  });

  it.each([-12, 0])("accepts original author residue numbering %s in an imported structure", (structure_position) => {
    const report = importedSpatialFixture();
    const response = importedResponse({ ...report,
      mapping: report.mapping.map((row, index) => index === 0 ? { ...row, structure_position, insertion_code: "B" } : row) });
    expect(load(response)).toBe(true);
  });

  it.each([1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1])(
    "rejects nonintegral or unsafe original author residue numbering: %s", (structure_position) => {
      const report = importedSpatialFixture();
      expect(load(importedResponse({ ...report,
        mapping: report.mapping.map((row) => ({ ...row, structure_position })) }))).toBe(false);
    },
  );

  it.each([
    { structure_format: "cif" }, { structure_format: undefined }, { source_sha256: "b".repeat(64) },
  ])("rejects a display format or original structure hash mismatch: %j", (patch) => {
    expect(load(importedResponse({ ...importedSpatialFixture(), ...patch }))).toBe(false);
  });

  it.each([
    { structure_member: "other-model.cif" }, { confidence_member: null }, { confidence_sha256: null },
    { display_kind: "original-structure" }, { interdomain_confidence: "high" },
  ])("rejects inconsistent original member provenance or unsupported claims: %j", (patch) => {
    expect(load(evidenceResponse(patch))).toBe(false);
  });

  it("accepts optional paired sequence provenance", () => {
    expect(load(evidenceResponse({ sequence_member: "query.a3m", sequence_sha256: "7".repeat(64) }))).toBe(true);
    expect(load(evidenceResponse({ sequence_member: null, sequence_sha256: null }))).toBe(true);
  });

  it.each([
    { sequence_member: "query.a3m" }, { sequence_sha256: "7".repeat(64) },
    { sequence_member: "query.a3m", sequence_sha256: null },
    { sequence_member: null, sequence_sha256: "7".repeat(64) },
  ])("rejects unpaired original sequence member/hash provenance: %j", (patch) => {
    expect(load(evidenceResponse(patch))).toBe(false);
  });
});

describe("prediction source notices RPC contract", () => {
  function acceptsNotices(notices: unknown) {
    return [inspect({ ...predictionBundleInventory(), notices }),
      load(evidenceResponse({ source_notices: notices }))];
  }

  it("accepts omitted, empty, and bounded source notices", () => {
    expect(acceptsNotices(undefined)).toEqual([true, true]);
    expect(acceptsNotices([])).toEqual([true, true]);
    expect(acceptsNotices([sourceNotice()])).toEqual([true, true]);
    expect(acceptsNotices(Array.from({ length: 256 }, sourceNotice))).toEqual([true, true]);
    expect(acceptsNotices([{ ...sourceNotice(), member: "m".repeat(4096), text: "t".repeat(262144) }])).toEqual([true, true]);
  });

  it.each([
    { notices: null }, { notices: {} }, { notices: [null] },
    { notices: [{ ...sourceNotice(), sha256: "bad-hash" }] },
    { notices: [{ ...sourceNotice(), member: "m".repeat(4097) }] },
    { notices: [{ ...sourceNotice(), text: "t".repeat(262145) }] },
    { notices: Array.from({ length: 257 }, sourceNotice) },
  ])("rejects malformed or oversized notice case %#", ({ notices }) => {
    expect(acceptsNotices(notices)).toEqual([false, false]);
  });
});
