import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  sendRequest: vi.fn(),
}));

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useAppStore } from "../appStore";
import type { SdmPrimerResult } from "../../types/models";

function primer(mutation: string): SdmPrimerResult {
  return {
    mutation,
    aa_position: 1,
    codon_pos: 0,
    forward_seq: "ATGC",
    reverse_seq: "GCAT",
    fwd_len: 20,
    rev_len: 20,
    overlap_len: 18,
    candidate_fwd_count: 1,
    candidate_rev_count: 1,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 4,
    has_offtarget: false,
    penalty: 0,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "ATG",
    mt_codon: "GCG",
    overlap_seq: "ATGC",
    warnings: [],
  };
}

const originalRetry = useAppStore.getState().retryFailedMutation;

afterEach(() => {
  mocks.sendRequest.mockReset();
  useAppStore.setState({ retryFailedMutation: originalRetry });
});

describe("retry design request contract", () => {
  it("includes the store overlap mode on retry requests", async () => {
    mocks.sendRequest.mockResolvedValue({ candidates: [] });
    useAppStore.setState({ overlapMode: "full" });

    await useAppStore.getState().retryFailedMutation("M1A", {
      tm_fwd_target: 62,
    });

    expect(mocks.sendRequest).toHaveBeenCalledWith(
      "retry_failed_mutation",
      expect.objectContaining({ overlap_mode: "full" }),
    );
  });

  it("mirrors the forward range after switching from asymmetric partial to full overlap", async () => {
    mocks.sendRequest.mockResolvedValue({ candidates: [] });
    useAppStore.setState({
      overlapMode: "partial",
      primerLenEnabled: true,
      fwdLenMin: 25,
      fwdLenMax: 45,
      revLenMin: 19,
      revLenMax: 27,
    });
    useAppStore.getState().setOverlapMode("full");

    await useAppStore.getState().retryFailedMutation("M1A", {
      tm_fwd_target: 62,
      fwd_len_min: 25,
      fwd_len_max: 45,
      rev_len_min: 19,
      rev_len_max: 27,
    });

    expect(mocks.sendRequest).toHaveBeenCalledWith(
      "retry_failed_mutation",
      expect.objectContaining({
        overlap_mode: "full",
        fwd_len_min: 25,
        fwd_len_max: 45,
        rev_len_min: 25,
        rev_len_max: 45,
      }),
    );
  });

  it("omits length limits from suggested retries when length limiting is off", async () => {
    const retry = vi.fn().mockResolvedValue([]);
    useAppStore.setState({
      retryFailedMutation: retry,
      primerLenEnabled: false,
      designResults: [primer("M1A")],
      failedMutations: [{ mutation: "M2A", rank: 1, reason: "No candidate" }],
    });

    await useAppStore.getState().autoRetryFailedWithSuggestion();

    expect(retry).toHaveBeenCalledWith(
      "M2A",
      expect.not.objectContaining({
        fwd_len_min: expect.anything(),
        fwd_len_max: expect.anything(),
        rev_len_min: expect.anything(),
        rev_len_max: expect.anything(),
      }),
    );
  });

  it("keeps the user's Tm and GC constraints for substitution retries", async () => {
    const retry = vi.fn().mockResolvedValue([]);
    useAppStore.setState({
      retryFailedMutation: retry,
      isDesigning: true,
      primerLenEnabled: false,
      designResults: [primer("M1A")],
      failedMutations: [{ mutation: "M10A", rank: 1, reason: "No candidate" }],
      poolVariants: ["M10V"],
      tmFwdTarget: 64,
      tmRevTarget: 59,
      tmOverlapTarget: 44,
      gcMin: 43,
      gcMax: 57,
    });

    await useAppStore.getState().cascadeFailedRetry("pipeline-fill");

    expect(retry).toHaveBeenCalledWith(
      "M10V",
      expect.objectContaining({
        tm_fwd_target: 64,
        tm_rev_target: 59,
        tm_overlap_target: 44,
        gc_min: 43,
        gc_max: 57,
      }),
    );
    for (const [, params] of retry.mock.calls) {
      expect(params).not.toHaveProperty("fwd_len_min");
      expect(params).not.toHaveProperty("fwd_len_max");
      expect(params).not.toHaveProperty("rev_len_min");
      expect(params).not.toHaveProperty("rev_len_max");
    }
  });
});
