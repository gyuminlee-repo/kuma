/**
 * Shared vi.fn() stand-ins for the sibling-slice functions inputSlice reaches
 * for through `get()`.
 *
 * inputSlice.*.test.ts builds its store double by calling `createInputSlice`
 * alone (see each file's `makeStore`), so anything owned by analysisSlice
 * (clearResults, setVerdicts, setLayoutProvenance, ...) is absent unless
 * supplied by hand; calling it throws "get(...).xxx is not a function" and
 * the analyze try/catch reports "Analysis failed" instead of the real error.
 * Three test files each hand-copied this list, and a new cross-slice call
 * from inputSlice (setLayoutProvenance/setMappingIntegrity, added alongside
 * clearResults) broke all three at once because the copies had drifted.
 * Importing this instead of relisting the functions means a future
 * inputSlice -> analysisSlice call only needs one new entry, here.
 */
import { vi } from "vitest";
import type { AppState } from "../../types";

export function createAnalysisSliceDoubles(): Partial<AppState> {
  return {
    setVerdicts: vi.fn(),
    setReplicates: vi.fn(),
    setSummary: vi.fn(),
    setAnalyzeYield: vi.fn(),
    setLayoutProvenance: vi.fn(),
    setMappingIntegrity: vi.fn(),
    setOutputPath: vi.fn(),
    setDistributionStats: vi.fn(),
    clearResults: vi.fn(),
    loadPlateData: vi.fn().mockResolvedValue(undefined),
    loadRunHealth: vi.fn().mockResolvedValue(undefined),
  };
}
