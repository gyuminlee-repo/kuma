import { describe, expect, it } from "vitest";
import {
  MIN_REPORTABLE_LOSS,
  diagnoseCoverageLoss,
} from "@/components/mame/widgets/CoverageLossNotice";

describe("diagnoseCoverageLoss", () => {
  it("claims nothing without counters", () => {
    expect(diagnoseCoverageLoss(null)).toBeNull();
    expect(diagnoseCoverageLoss({})).toBeNull();
    expect(diagnoseCoverageLoss({ passed_mapq: 100 })).toBeNull();
    expect(diagnoseCoverageLoss({ passed_coverage: 100 })).toBeNull();
  });

  it("leaves both all-or-nothing cases to EmptyAnalysisNotice", () => {
    // Nothing aligned: that notice calls it "noAlignment".
    expect(
      diagnoseCoverageLoss({ passed_mapq: 0, passed_coverage: 0 }),
    ).toBeNull();
    // Aligned but nothing survived coverage: its "noCoverage".
    expect(
      diagnoseCoverageLoss({ passed_mapq: 5000, passed_coverage: 0 }),
    ).toBeNull();
  });

  it("stays quiet when the run kept essentially everything", () => {
    expect(
      diagnoseCoverageLoss({ passed_mapq: 1000, passed_coverage: 1000 }),
    ).toBeNull();
    expect(
      diagnoseCoverageLoss({ passed_mapq: 1000, passed_coverage: 900 }),
    ).toBeNull();
  });

  it("reports the discarded share once it crosses the threshold", () => {
    const lost = diagnoseCoverageLoss({
      passed_mapq: 1000,
      passed_coverage: 600,
    });
    expect(lost).toBeCloseTo(0.4, 10);
  });

  it("treats the threshold itself as reportable", () => {
    const mapq = 1000;
    const kept = mapq * (1 - MIN_REPORTABLE_LOSS);
    expect(
      diagnoseCoverageLoss({ passed_mapq: mapq, passed_coverage: kept }),
    ).toBeCloseTo(MIN_REPORTABLE_LOSS, 10);
  });

  it("reports the plate that prompted this notice", () => {
    // The CloneFlow comparison: a third of the wells returned nothing while
    // holding reads, because a constant ~28 bp shortfall at the reference 3'
    // end fails a fractional gate on short amplicons.
    const lost = diagnoseCoverageLoss({
      passed_mapq: 96,
      passed_coverage: 62,
    });
    expect(lost).not.toBeNull();
    expect(lost as number).toBeGreaterThan(MIN_REPORTABLE_LOSS);
  });

  it("does not invent a negative loss when coverage exceeds mapq", () => {
    expect(
      diagnoseCoverageLoss({ passed_mapq: 100, passed_coverage: 120 }),
    ).toBeNull();
  });
});
