import { describe, expect, it } from "vitest";
import { domainSelectionDistribution, formatDomainPositions } from "./domainAnnotation";
import { domainResultFixture } from "@/test-utils/domainAnnotationFixture";

describe("annotation-only distribution", () => {
  it("counts substitutions and unique sites separately, with discontinuous domains and unassigned residues", () => {
    const variants = ["A2V", "A2G", "A3V", "A4G"];
    const summary = domainSelectionDistribution(domainResultFixture(), "MAAAA", variants);
    expect(summary?.[0]).toEqual({ residueCount: 3, variantCount: 3, siteCount: 2, fraction: 0.75, variants: ["A2V", "A2G", "A4G"] });
    expect(summary?.[1]).toEqual({ residueCount: 2, variantCount: 1, siteCount: 1, fraction: 0.25, variants: ["A3V"] });
    expect(variants).toEqual(["A2V", "A2G", "A3V", "A4G"]);
    expect(formatDomainPositions([1, 2, 4])).toBe("1–2, 4");
  });
  it.each([["A2V", "A2V"], ["M2V"], ["A2V/A3G"], ["A7G"], ["A2A"]])("fails closed for unsupported selected variants %j", (...variants) => {
    expect(domainSelectionDistribution(domainResultFixture(), "MAAAA", variants)).toBeNull();
  });
  it("does not invent a percentage with an empty selected set", () => {
    expect(domainSelectionDistribution(domainResultFixture(), "MAAAA", [])?.map((row) => row.fraction)).toEqual([null, null]);
  });
});
