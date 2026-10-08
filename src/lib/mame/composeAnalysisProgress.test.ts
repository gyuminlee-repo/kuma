import { describe, it, expect } from "vitest";
import { composeAnalysisProgress } from "./composeAnalysisProgress";

describe("composeAnalysisProgress", () => {
  it("maps demux raw progress to 0-50 range in raw_run mode", () => {
    expect(composeAnalysisProgress(0, "demux", true)).toBe(0);
    expect(composeAnalysisProgress(50, "demux", true)).toBe(25);
    expect(composeAnalysisProgress(100, "demux", true)).toBe(50);
  });

  it("maps analyze raw progress to 50-100 range in raw_run mode", () => {
    expect(composeAnalysisProgress(0, "analyze", true)).toBe(50);
    expect(composeAnalysisProgress(50, "analyze", true)).toBe(75);
    expect(composeAnalysisProgress(100, "analyze", true)).toBe(100);
  });

  it("keeps analyze raw progress 0-100 when not raw_run", () => {
    expect(composeAnalysisProgress(0, "analyze", false)).toBe(0);
    expect(composeAnalysisProgress(50, "analyze", false)).toBe(50);
    expect(composeAnalysisProgress(100, "analyze", false)).toBe(100);
  });

  it("clamps out-of-range input", () => {
    expect(composeAnalysisProgress(-10, "demux", true)).toBe(0);
    expect(composeAnalysisProgress(110, "analyze", true)).toBe(100);
  });

  it("monotonicity: demux ceiling (50) equals analyze floor (50) in raw_run", () => {
    expect(composeAnalysisProgress(100, "demux", true)).toBe(50);
    expect(composeAnalysisProgress(0, "analyze", true)).toBe(50);
  });
});
