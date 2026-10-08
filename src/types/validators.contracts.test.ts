import { describe, expect, it } from "vitest";
import { getRpcResultValidator } from "@/types/validators";
import { isMameContext, legacySampleMapPointer } from "@/types/mame/mame_context";
import type { WorkspaceV3 } from "@/types/models";

function workspace(): WorkspaceV3 {
  return {
    schema_version: "0.3",
    inputs: { fastaPath: "", mutationInputMode: "text", mutationText: "", evolveproCsvPath: "", selectedGene: "" },
    settings: { codonStrategy: "closest", maxPrimers: 96, tmFwdTarget: 60, tmRevTarget: 60, tmOverlapTarget: 60, gcMin: 30, gcMax: 70 },
    results: { designResults: [], successCount: 0, totalCount: 0, failedMutations: [], plateMappings: [], dedupInfo: {}, manuallySwapped: {}, customCandidates: {} },
    ui: { tableSorting: [] },
    rounds: [{ id: "round-1", n: 1, created_at: "2026-09-17T00:00:00Z", status: "design", error_info: null, plate_meta: { plates: [] }, design: {}, genotype: {}, activity: null, merged_table: [] }],
    active_round_id: "round-1",
  };
}

describe("FC-05 real RPC guards: reject malformed declared fields", () => {
  const validate = getRpcResultValidator("load_workspace");
  it("CONTROL accepts a complete round and rejects a non-array rounds field", () => {
    expect(validate(workspace())).toBe(true);
    expect(validate({ ...workspace(), rounds: null })).toBe(false);
    expect(validate({ ...workspace(), inputs: null })).toBe(false);
  });
  it.each([
    { id: 42 }, { status: "unknown" }, { n: "1" }, { created_at: null },
    { error_info: { stage: "unknown", message: "x", occurred_at: "now" } },
    { plate_meta: { plates: [null] } }, { design: [] }, { genotype: null },
    { activity: { records: [42], plate_meta: { plates: [] } } },
    { merged_table: [null] }, { evolvepro_input: { path: 42, produced_at: "now" } },
    { advisory: { result: {}, inputs: [], decided_at: "now", input_signature: "x" } },
  ])("FC-05 rejects corrupted round fields %j", (fields) => {
    const valid = workspace();
    expect(validate({ ...valid, rounds: [{ ...valid.rounds[0], ...fields }] })).toBe(false);
  });
  it.each(["tmTolerance", "structureAccession", "structureLoaded"])("FC-05 checks optional %s", (field) => {
    const valid = workspace();
    expect(validate({ ...valid, settings: { ...valid.settings, [field]: {} } })).toBe(false);
  });
  it("accepts declared settings, optional paths and nested round content", () => {
    const valid = workspace();
    valid.settings = { ...valid.settings, evolveproMode: "others", overlapMode: "full", randomSeed: null,
      echoTransferVol: 25, echoQuadrant: "A1", echoUsedQuadrants: ["B1"], janusTransferVol: 10,
      tmTolerance: 3, structureAccession: "test", structureLoaded: false };
    valid.inputs.othersSourcePath = "source.csv";
    valid.rounds[0].evolvepro_input = { path: "out.xlsx", produced_at: "now", wt_values: [1], variant_replicates: { A1V: [2] } };
    valid.rounds[0].advisory = { result: { advisory: "decision", label: "stop", reason: "test", confidence: null, missing_inputs: [] },
      inputs: [{ n: 1, path: "out.xlsx", wt_values: [1] }], decided_at: "now", input_signature: "x" };
    expect(validate(valid)).toBe(true);
  });
  it.each([null, 42, {}])("rejects invalid round element %j", (round) => {
    const payload: unknown = { ...workspace(), rounds: [round] };
    expect(validate(payload)).toBe(false);

  });
  it.each(["evolveproMode", "overlapMode", "randomSeed", "echoTransferVol", "echoQuadrant", "echoUsedQuadrants", "janusTransferVol"])("rejects malformed declared settings field %s", (field) => {
    const valid = workspace();
    expect(validate({ ...valid, settings: { ...valid.settings, [field]: { invalid: true } } })).toBe(false);
  });
  it("rejects an object as othersSourcePath", () => {
    const valid = workspace();
    expect(validate({ ...valid, inputs: { ...valid.inputs, othersSourcePath: {} } })).toBe(false);
  });
  it("rejects invalid interface positions", () => {
    const positions = getRpcResultValidator("fetch_interface_residues");
    expect(positions({ interface_positions: [1, 2], source: "pdb" })).toBe(true);
    expect(positions({ interface_positions: null, source: "pdb" })).toBe(false);
    expect(positions({ interface_positions: [null, "wrong"], source: "pdb" })).toBe(false);
  });
  it("rejects invalid export result elements", () => {
    const exports = getRpcResultValidator("export_all");
    expect(exports({ success: ["out.csv"], failed: [{ path: "x", reason: "denied" }], output_dir: "/audit" })).toBe(true);
    expect(exports({ success: null, failed: [], output_dir: "/audit" })).toBe(false);
    expect(exports({ success: [42], failed: [null], output_dir: "/audit" })).toBe(false);
  });
});

describe("FC-06 real MAME context guard", () => {
  it.each([
    { schema: 2 }, { schema: 2, published_at: 42 },
    { schema: 2, published_at: "now", custom_barcodes_path: {} },
    { schema: 2, published_at: "now", reference_path: null },
    { schema: 1, published_at: "now", sample_map_template_path: 42 },
  ])("rejects malformed context %j", (context) => {
    expect(isMameContext(context)).toBe(false);
  });
  it("CONTROL accepts valid contexts, retains legacy pointer, rejects absent/string schema", () => {
    const old = { schema: 1, published_at: "2026-09-17", sample_map_template_path: "old.xlsx" };
    expect(isMameContext(old)).toBe(true);
    expect(legacySampleMapPointer(old)).toBe("old.xlsx");
    expect(isMameContext({ schema: 2, published_at: "2026-09-17", reference_path: "ref.fa" })).toBe(true);
    expect(isMameContext(null)).toBe(false);
    expect(isMameContext({})).toBe(false);
    expect(isMameContext({ schema: "2" })).toBe(false);
  });
  it("rejects missing published_at and numeric reference_path", () => {
    const payload: unknown = { schema: 2, reference_path: 42 };
    expect(isMameContext(payload)).toBe(false);

  });
});
