/**
 * sampleData.test.ts
 *
 * Sample mode takes its verdicts from this mock, not from the bundled JSON
 * fixture, so a field the sidecar starts sending has to be added here as well
 * or the demo quietly stops exercising the UI that reads it. These assertions
 * pin the two Confidence-popup inputs and the invariants that make them
 * readable.
 */

import { describe, expect, it } from "vitest";
import { sampleVerdicts } from "./sampleData";

describe("sampleVerdicts confidence fields", () => {
  it("gives every well a noise floor no higher than its own maximum", () => {
    for (const v of sampleVerdicts()) {
      const floor = v.median_minor_allele_fraction;
      if (floor === undefined) {
        throw new Error(`${v.custom_barcode} carries no noise floor`);
      }
      expect(floor).toBeLessThanOrEqual(v.max_minor_allele_fraction);
    }
  });

  it("states the N-fraction basis on every well and withholds it on one", () => {
    const verdicts = sampleVerdicts();
    for (const v of verdicts) {
      expect(v.consensus_n_fraction_evaluable).toBeDefined();
    }
    const substituted = verdicts.filter(
      (v) => v.consensus_n_fraction_evaluable === false,
    );
    expect(substituted.map((v) => v.verdict)).toEqual(["FRAMESHIFT"]);
    // `false` means 0.0 stood in for a fraction that could not be recovered, so
    // a non-zero fraction beside it would contradict the flag.
    for (const v of substituted) {
      expect(v.consensus_n_fraction).toBe(0);
    }
  });
});
