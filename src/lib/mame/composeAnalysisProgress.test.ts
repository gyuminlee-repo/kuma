import { describe, it, expect } from "vitest";
import { composeAnalysisProgress } from "./composeAnalysisProgress";

describe("composeAnalysisProgress", () => {
  it("maps sort raw progress to 0-50 range", () => {
    expect(composeAnalysisProgress(0, "sort")).toBe(0);
    expect(composeAnalysisProgress(50, "sort")).toBe(25);
    expect(composeAnalysisProgress(100, "sort")).toBe(50);
  });

  it("maps analyze raw progress to 50-100 range in raw_run mode", () => {
    expect(composeAnalysisProgress(0, "analyze", "raw_run")).toBe(50);
    expect(composeAnalysisProgress(50, "analyze", "raw_run")).toBe(75);
    expect(composeAnalysisProgress(100, "analyze", "raw_run")).toBe(100);
  });

  it("keeps analyze raw progress 0-100 in barcode mode", () => {
    expect(composeAnalysisProgress(0, "analyze", "barcode")).toBe(0);
    expect(composeAnalysisProgress(50, "analyze", "barcode")).toBe(50);
    expect(composeAnalysisProgress(100, "analyze", "barcode")).toBe(100);
  });
});
