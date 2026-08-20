import { describe, expect, it } from "vitest";
import { diagnoseNoControlWell } from "@/components/mame/widgets/NoControlWellNotice";

describe("diagnoseNoControlWell", () => {
  it("says nothing before anything has been read", () => {
    expect(diagnoseNoControlWell(null, null)).toBe(false);
  });

  it("says nothing when the draft carries a control well", () => {
    expect(diagnoseNoControlWell("H12", 24)).toBe(false);
  });

  it("says nothing when the capacity gate emptied the draft", () => {
    // dropped_mutant_ids non-empty -> layout={} -> wt_well null and count 0.
    // Nothing was placed, so this is not "placed with no control".
    expect(diagnoseNoControlWell(null, 0)).toBe(false);
  });

  it("reports a loaded, non-empty draft with no control well", () => {
    // A Well-column source with no wild-type row, or wt_placement: "none".
    expect(diagnoseNoControlWell(null, 24)).toBe(true);
  });
});
