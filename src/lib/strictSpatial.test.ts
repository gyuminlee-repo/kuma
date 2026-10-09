import { describe, expect, it } from "vitest";
import { useAppStore } from "@/store/appStore";
import { strictSpatialFixture } from "@/test-utils/strictSpatialFixture";
import { currentStrictSpatialResult, strictSpatialContextKey } from "./strictSpatial";

function state() {
  const result = strictSpatialFixture();
  const input = { ...useAppStore.getState(), strictSpatialEnabled: true,
    structuralDiversityEnabled: true, evolveproMode: "pipeline" as const,
    mutationInputMode: "evolvepro" as const, maxPrimers: 2,
    structureAccession: result.source_accession, evolveproCsvPath: "/tmp/pool.csv",
    evolveproSelectedVariants: result.selected_variants,
  };
  return { ...input, strictSpatialSelection: { result, contextKey: strictSpatialContextKey(input) } };
}

describe("strict spatial selection freshness", () => {
  it("accepts only the verified current set, not a ranked fallback", () => {
    const input = state();
    expect(currentStrictSpatialResult(input)).toBe(input.strictSpatialSelection.result);
    expect(currentStrictSpatialResult({ ...input, evolveproSelectedVariants: [] })).toBeNull();
    expect(currentStrictSpatialResult({ ...input, evolveproSelectedVariants: ["A2G", "A5V"] })).toBeNull();
  });
  it.each([
    { structureAccession: "P99999" }, { maxPrimers: 3 }, { evolveproCsvPath: "/tmp/other.csv" },
    { evolveproScoreOrder: "asc" as const }, { strictSpatialEnabled: false },
    { structuralDiversityEnabled: false }, { evolveproMode: "topN" as const },
  ])("invalidates after an input changes: %j", (patch) => {
    expect(currentStrictSpatialResult({ ...state(), ...patch })).toBeNull();
  });
});
