/**
 * pickAnalyzeYield, the narrowing that stands between the analyze response and
 * the zero-result explanation. A gate counter it drops never reaches the notice,
 * so the pass-through is fixed here rather than only through the rendered view.
 */
import { describe, it, expect } from "vitest";
import { pickAnalyzeYield } from "./analyzeYield";

describe("pickAnalyzeYield", () => {
  it("keeps the demux gate counters even when the legacy yield fields are absent", () => {
    expect(pickAnalyzeYield({ total_reads: 48000, passed_mapq: 0, passed_coverage: 0 })).toEqual({
      total_reads: 48000,
      passed_mapq: 0,
      passed_coverage: 0,
    });
  });

  it("keeps every yield field the response carried", () => {
    expect(
      pickAnalyzeYield({
        assigned_reads: 12,
        wells_with_reads: 3,
        total_reads: 48000,
        passed_mapq: 31500,
        passed_coverage: 0,
      }),
    ).toEqual({
      assigned_reads: 12,
      wells_with_reads: 3,
      total_reads: 48000,
      passed_mapq: 31500,
      passed_coverage: 0,
    });
  });

  it("omits absent fields rather than defaulting them to 0", () => {
    const picked = pickAnalyzeYield({ assigned_reads: 0 });
    expect(picked).toEqual({ assigned_reads: 0 });
    expect(picked === null ? [] : Object.keys(picked)).toEqual(["assigned_reads"]);
  });

  it("returns null when the response carried no yield field at all (consensus-dir)", () => {
    expect(pickAnalyzeYield({})).toBeNull();
  });
});
