/**
 * validation.test.ts — Spec #18: Next-click 필수 입력 검증 단위 테스트.
 */
import { describe, it, expect } from "vitest";
import { validateForNext } from "@/store/validation";
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
