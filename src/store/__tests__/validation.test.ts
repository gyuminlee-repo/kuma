/**
 * validation.test.ts — Spec #18: Next-click 필수 입력 검증 단위 테스트.
 */
import { describe, it, expect } from "vitest";
import { validateForNext, validateForRun } from "@/store/validation";
import type { AppState } from "@/store/types";

function state(partial: Partial<AppState>): AppState {
  return partial as AppState;
}

describe("validateForNext", () => {
  describe("design.load", () => {
    it("returns missing sequence when seqInfo is null", () => {
      const result = validateForNext("design.load", state({ seqInfo: null }));
      expect(result.ok).toBe(false);
      expect(result.missing).toContain("validation.missing.sequence");
    });

    it("returns ok when seqInfo is set", () => {
      const result = validateForNext(
        "design.load",
        state({ seqInfo: { length: 100 } as never }),
      );
      expect(result.ok).toBe(true);
      expect(result.missing).toEqual([]);
    });
  });

  describe("design.mutation", () => {
    it("returns missing when both mutationText empty and evolveproTotalCount 0", () => {
      const result = validateForNext(
        "design.mutation",
        state({ mutationText: "", evolveproTotalCount: 0 }),
      );
      expect(result.ok).toBe(false);
      expect(result.missing).toContain("validation.missing.mutation");
    });

    it("returns missing when mutationText only whitespace and evolveproTotalCount 0", () => {
      const result = validateForNext(
        "design.mutation",
        state({ mutationText: "   \n  ", evolveproTotalCount: 0 }),
      );
      expect(result.ok).toBe(false);
    });

    it("returns ok when mutationText non-empty", () => {
      const result = validateForNext(
        "design.mutation",
        state({ mutationText: "A1T", evolveproTotalCount: 0 }),
      );
      expect(result.ok).toBe(true);
    });

    it("returns ok when evolveproTotalCount > 0", () => {
      const result = validateForNext(
        "design.mutation",
        state({ mutationText: "", evolveproTotalCount: 5 }),
      );
      expect(result.ok).toBe(true);
    });
  });

  describe("other substeps", () => {
    it("design.params returns ok regardless of state", () => {
      expect(validateForNext("design.params", state({})).ok).toBe(true);
    });
    it("design.submit returns ok", () => {
      expect(validateForNext("design.submit", state({})).ok).toBe(true);
    });
    it("output.summary returns ok", () => {
      expect(validateForNext("output.summary", state({})).ok).toBe(true);
    });
    it("export.all returns ok", () => {
      expect(validateForNext("export.all", state({})).ok).toBe(true);
    });
  });
});

/**
 * validateForRun, Run Design 게이트.
 *
 * 게이트는 하나이고, "넘어가도 되는가" 와 "돌려도 되는가" 의 차이는 이 파일
 * 안에만 적혀 있다. 실행 쪽이 조건을 따로 적으면 마법사는 통과시키는데 Run
 * Design 은 막힌 채 아무 말도 안 하는 상태가 다시 생긴다.
 */
describe("validateForRun", () => {
  const seqInfo = { header: "t", seq_length: 100, genes: [] } as never;
  const twoGenes = {
    header: "t",
    seq_length: 100,
    genes: [{ cds_start: 0 }, { cds_start: 50 }],
  } as never;

  it("requires the sequence", () => {
    const result = validateForRun(state({ seqInfo: null, mutationText: "A1T" }));
    expect(result.ok).toBe(false);
    expect(result.missing).toContain("appLayout.missingSeqFile");
  });

  it("requires resolved mutations even when a pool is loaded", () => {
    // The engine reads mutationText and nothing else (designSlice.ts:179), so an
    // EVOLVEpro count is a reason to advance, not a reason to run.
    const advancing = state({ mutationText: "", evolveproTotalCount: 5 });
    expect(validateForNext("design.mutation", advancing).ok).toBe(true);

    const running = validateForRun(state({ seqInfo, mutationText: "", evolveproTotalCount: 5 }));
    expect(running.ok).toBe(false);
    expect(running.missing).toContain("appLayout.missingMutations");
  });

  it("requires a target gene when the sequence carries several", () => {
    const result = validateForRun(
      state({ seqInfo: twoGenes, mutationText: "A1T", selectedGene: "" }),
    );
    expect(result.ok).toBe(false);
    expect(result.missing).toContain("appLayout.missingTargetGene");
  });

  it("passes once the sequence and the mutations are both there", () => {
    const passing = state({ seqInfo, mutationText: "A1T", evolveproTotalCount: 0 });
    expect(validateForRun(passing).ok).toBe(true);
    // Running is strictly stronger: anything runnable is also advanceable.
    expect(validateForNext("design.mutation", passing).ok).toBe(true);
  });
});
