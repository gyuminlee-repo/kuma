import { describe, expect, it } from "vitest";
import { useAppStore } from "@/store/appStore";
import { strictSpatialFixture } from "@/test-utils/strictSpatialFixture";
import { currentStrictSpatialResult, strictSpatialContextKey } from "./strictSpatial";

const DOMAINS = [
  { name: "Linker", id: "PF00001", start: 10, end: 24, db: "Pfam" },
  { name: "Core", id: "PF00002", start: 30, end: 60, db: "Pfam" },
];

function state() {
  const result = strictSpatialFixture();
  const input = { ...useAppStore.getState(), strictSpatialEnabled: true,
    structuralDiversityEnabled: true, evolveproMode: "pipeline" as const,
    mutationInputMode: "evolvepro" as const, maxPrimers: 2,
    strictSpatialBudgetMode: "unique_sites" as const, strictSpatialSiteCap: null,
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
    { strictSpatialBudgetMode: "distinct_variants" as const }, { strictSpatialSiteCap: 2 },
    { refDomains: DOMAINS, disabledDomains: ["Linker-10"] },
  ])("invalidates after an input changes: %j", (patch) => {
    expect(currentStrictSpatialResult({ ...state(), ...patch })).toBeNull();
  });
  it("keys the certificate to the ranges the user disabled", () => {
    const base = { ...state(), refDomains: DOMAINS };
    const none = strictSpatialContextKey(base);
    const one = strictSpatialContextKey({ ...base, disabledDomains: ["Linker-10"] });
    const other = strictSpatialContextKey({ ...base, disabledDomains: ["Core-30"] });
    expect(one).not.toBe(none);
    expect(other).not.toBe(one);
    expect(strictSpatialContextKey({ ...base, disabledDomains: ["Linker-10"] })).toBe(one);
  });
  it("rejects an echoed policy that does not match the current budget", () => {
    const input = state();
    input.strictSpatialSelection.result = { ...input.strictSpatialSelection.result, budget_mode: "distinct_variants" };
    expect(currentStrictSpatialResult(input)).toBeNull();
  });
});
