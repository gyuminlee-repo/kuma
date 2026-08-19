/**
 * A declared string union is enforced, not decorated.
 *
 * `isString` on a field the type declares as a four-value union admits every
 * string, so a fifth value reaches whatever switches on it. For
 * `strategy.classify_round` that is not hypothetical: AdvisoryDecisionCard
 * renders `label` through `t("advisoryDecision.labels.<label>")` with no
 * membership check of its own, so an out-of-union label lands on the decision
 * badge as an i18n key miss.
 *
 * Each case here is a payload that is well-formed in every respect EXCEPT one
 * union member, so it isolates the membership check from the shape check.
 */

import { describe, expect, it } from "vitest";

import { getMameRpcResultValidator } from "./validators";

const CLASSIFY = "strategy.classify_round";
const BUILD_EVOLVEPRO = "mame.activity.build_evolvepro_input";

function validate(method: string, payload: unknown): boolean {
  const guard = getMameRpcResultValidator(method);
  if (!guard) throw new Error(`no validator registered for ${method}`);
  return guard(payload);
}

/** `python-core/sidecar_mame/handlers/classify_round.py:614-620`. */
function decisionResult(overrides: Record<string, unknown> = {}) {
  return {
    advisory: "decision",
    label: "continue_walking",
    reason: "signals_agree",
    confidence: 0.87,
    missing_inputs: [],
    ...overrides,
  };
}

/** `python-core/sidecar_mame/handlers/classify_round.py:605-612`. */
function notAssessableResult(overrides: Record<string, unknown> = {}) {
  return {
    advisory: "not_assessable",
    reason: "wt_replicates_missing",
    missing_inputs: ["wt_replicates"],
    blocked_decisions: ["switch_combinatorial", "stop"],
    wt_replicate_count: 0,
    wt_replicate_min: 3,
    ...overrides,
  };
}

/** `kuma_core/mame/activity/build_evolvepro_input.py:463-480`. */
function buildEvolveproResult(overrides: Record<string, unknown> = {}) {
  return {
    output_path: "/tmp/out.xlsx",
    n_variants: 12,
    n_authoritative: 10,
    n_fallback_only: 2,
    warnings: [],
    mismatched: [],
    n_ngs_excluded: 0,
    ngs_excluded: [],
    gc_export_path: "",
    label_audit: null,
    manifest_path: "/tmp/out.xlsx.manifest.json",
    primary_format: "activity_path",
    input_count: 12,
    evaluable_count: 12,
    exclusion_reason_counts: {},
    normalization_sources: ["activity_path:raw"],
    evidence_hash: "abc",
    artifact_hashes: {},
    wt_values: [1.0, 0.98, 1.02],
    variant_replicates: { "5F": [1.48, 1.52], "10L": [0.61] },
    ...overrides,
  };
}

/** `kuma_core/mame/activity/label_audit.py:240-245`. */
function labelAudit(overrides: Record<string, unknown> = {}) {
  return {
    discordant: [],
    n_checked: 8,
    n_unevaluable: 0,
    is_closed_permutation: false,
    cycles: [],
    geometry: null,
    ...overrides,
  };
}

describe("strategy.classify_round enforces its declared unions", () => {
  it("accepts both shapes the handler actually returns", () => {
    expect(validate(CLASSIFY, decisionResult())).toBe(true);
    expect(validate(CLASSIFY, notAssessableResult())).toBe(true);
  });

  it("accepts every label kuma_core/strategy/classify.py:68 declares", () => {
    for (const label of ["continue_walking", "switch_combinatorial", "stop", "deferred"]) {
      expect(validate(CLASSIFY, decisionResult({ label }))).toBe(true);
    }
  });

  it("refuses a label outside DecisionLabel", () => {
    // The exact payload that reached the badge as `advisoryDecision.labels.abandon_project`.
    expect(validate(CLASSIFY, decisionResult({ label: "abandon_project" }))).toBe(false);
  });

  it("refuses a not_assessable reason outside NotAssessableReason", () => {
    expect(validate(CLASSIFY, notAssessableResult({ reason: "who_knows" }))).toBe(false);
    // Both real values still pass.
    expect(validate(CLASSIFY, notAssessableResult({ reason: "wt_replicates_insufficient" }))).toBe(
      true,
    );
  });

  it("refuses an out-of-union entry in blocked_decisions", () => {
    // blocked_decisions renders through the same i18n keys as `label`, so one
    // bad element is enough to put a raw code in the sentence.
    expect(
      validate(CLASSIFY, notAssessableResult({ blocked_decisions: ["stop", "abandon_project"] })),
    ).toBe(false);
  });

  it("still accepts a free-form decision reason", () => {
    // `Decision.reason` is a bare `str` (kuma_core/strategy/classify.py:75), so
    // enumerating it here would refuse payloads the classifier legitimately sends.
    expect(validate(CLASSIFY, decisionResult({ reason: "some_new_code_added_later" }))).toBe(true);
  });
});

describe("build_evolvepro_input enforces its declared unions", () => {
  it("accepts every primary_format build_evolvepro_input.py:364 can pick", () => {
    for (const primary_format of ["activity_path", "gc_data_xlsx", "round1_report_xlsx"]) {
      expect(validate(BUILD_EVOLVEPRO, buildEvolveproResult({ primary_format }))).toBe(true);
    }
  });

  it("refuses replicates that are not numbers", () => {
    // These reach step 4.2 as the record of how many measurements produced each
    // exported activity. A string here would be counted as a replicate and
    // weighted like one.
    expect(
      validate(BUILD_EVOLVEPRO, buildEvolveproResult({
        variant_replicates: { "5F": [1.48, "1.52"] },
      })),
    ).toBe(false);
  });

  it("refuses a non-finite replicate", () => {
    // NaN passes a bare typeof check and then poisons any mean or spread taken
    // over the list.
    expect(
      validate(BUILD_EVOLVEPRO, buildEvolveproResult({
        variant_replicates: { "5F": [1.48, Number.NaN] },
      })),
    ).toBe(false);
  });

  it("refuses a bare number where a list belongs", () => {
    // The mean alone is what the workbook already holds, and recording it here
    // would look like replicates while carrying none.
    expect(
      validate(BUILD_EVOLVEPRO, buildEvolveproResult({
        variant_replicates: { "5F": 1.5 },
      })),
    ).toBe(false);
  });

  it("accepts an empty map, which is a build that exported nothing", () => {
    expect(
      validate(BUILD_EVOLVEPRO, buildEvolveproResult({ variant_replicates: {} })),
    ).toBe(true);
  });

  it("refuses replicates supplied as an array rather than a map", () => {
    // Object.values of an array is its elements, so a guard written without an
    // array check would accept this and lose the variant each list belongs to.
    expect(
      validate(BUILD_EVOLVEPRO, buildEvolveproResult({
        variant_replicates: [[1.48, 1.52]],
      })),
    ).toBe(false);
  });

  it("refuses a primary_format no source name produces", () => {
    expect(validate(BUILD_EVOLVEPRO, buildEvolveproResult({ primary_format: "csv" }))).toBe(false);
  });

  it("accepts every geometry _classify_geometry returns, and null", () => {
    for (const geometry of [
      "two_swap",
      "contiguous_shift",
      "scattered",
      "global_offset",
      null,
    ]) {
      expect(
        validate(BUILD_EVOLVEPRO, buildEvolveproResult({ label_audit: labelAudit({ geometry }) })),
      ).toBe(true);
    }
  });

  it("refuses a geometry outside the four buckets", () => {
    expect(
      validate(
        BUILD_EVOLVEPRO,
        buildEvolveproResult({ label_audit: labelAudit({ geometry: "diagonal" }) }),
      ),
    ).toBe(false);
  });

  it("accepts every LabelFinding category label_audit.py assigns", () => {
    for (const category of [
      "not_introduced",
      "wrong_residue",
      "extra_mutation",
      "sequence_collapse",
      "cross_well",
    ]) {
      const finding = {
        well: "A1",
        expected: "D12N",
        observed: ["D12N"],
        category,
        verdict: "PASS",
      };
      expect(
        validate(
          BUILD_EVOLVEPRO,
          buildEvolveproResult({ label_audit: labelAudit({ discordant: [finding] }) }),
        ),
      ).toBe(true);
    }
  });

  it("refuses a LabelFinding category outside the five buckets", () => {
    const finding = {
      well: "A1",
      expected: "D12N",
      observed: ["D12N"],
      category: "mystery",
      verdict: "PASS",
    };
    expect(
      validate(
        BUILD_EVOLVEPRO,
        buildEvolveproResult({ label_audit: labelAudit({ discordant: [finding] }) }),
      ),
    ).toBe(false);
  });
});
