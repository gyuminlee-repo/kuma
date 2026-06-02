import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-evolvepro", () => ({
  cancelEvolveProRun: vi.fn(),
  detectEvolveProEnv: vi.fn(),
  esm2CheckInstalled: vi.fn(),
  esm2DownloadCancel: vi.fn(),
  esm2DownloadStart: vi.fn(),
  getEmbeddingCacheStatus: vi.fn(),
  recommendEsm2Model: vi.fn(),
  setProgressHandler: vi.fn(),
  startEvolveProRun: vi.fn(),
}));

import { useEvolveProStore } from "./evolveProStore";
import type { EvolveProRunProgress, EvolveProRunResult } from "@/types/models.evolvepro";

describe("useEvolveProStore", () => {
  beforeEach(() => {
    useEvolveProStore.setState({
      evolveProEnvStatus: null,
      evolveProRunId: null,
      esm2Recommendation: null,
      evolveProProgress: null,
      evolveProProgressLog: [],
      evolveProResult: null,
      evolveProRunResult: null,
      evolveProError: null,
      evolveProDetecting: false,
      evolveProRunning: false,
      evolveProCancelling: false,
      evolveProRunStartedAt: null,
      esm2RecommendationLoading: false,
      esm2Downloads: {},
      esm2Installed: {},
      activeEsm2ModelId: null,
      embeddingCacheStatus: null,
      embeddingCacheLoading: false,
      evolveProRoundFiles: [],
      evolveProWtFasta: "",
      evolveProWtSequence: "",
      evolveProOutputDir: "",
      evolveProTopN: 0,
    });
    vi.clearAllMocks();
  });

  it("keeps loading state until a done progress snapshot arrives", () => {
    useEvolveProStore.setState({ evolveProRunning: true });

    const loading: EvolveProRunProgress = {
      run_id: "run-1",
      stage: "loading",
      current: 1,
      total: 3,
      message: "loading",
    };

    useEvolveProStore.getState().setProgress(loading);

    expect(useEvolveProStore.getState().evolveProProgress).toEqual(loading);
    expect(useEvolveProStore.getState().evolveProRunning).toBe(true);
  });

  it("stores the done result payload and clears running state", () => {
    useEvolveProStore.setState({ evolveProRunning: true });

    const done = {
      run_id: "run-1",
      stage: "done",
      current: 3,
      total: 3,
      message: "done",
      result: {
        run_id: "run-1",
        output_csv: "/tmp/out.csv",
        top_variants: ["A1V"],
        elapsed_sec: 12.5,
      },
    } satisfies EvolveProRunProgress & { result: EvolveProRunResult };

    useEvolveProStore.getState().setProgress(done);

    expect(useEvolveProStore.getState().evolveProResult).toEqual(done.result);
    expect(useEvolveProStore.getState().evolveProRunning).toBe(false);
  });

  it("keeps visible EVOLVEpro progress messages after the done snapshot", () => {
    useEvolveProStore.setState({ evolveProRunning: true });

    useEvolveProStore.getState().setProgress({
      run_id: "run-1",
      stage: "embedding",
      current: 14,
      total: 152,
      message: "batch 14/152 done | 2607.7 tok/s | ETA 12s",
    });
    useEvolveProStore.getState().setProgress({
      run_id: "run-1",
      stage: "done",
      current: 1,
      total: 1,
      message: "EVOLVEpro run finished",
    });

    expect(useEvolveProStore.getState().evolveProProgressLog).toEqual([
      "batch 14/152 done | 2607.7 tok/s | ETA 12s",
      "EVOLVEpro run finished",
    ]);
  });
});
