/**
 * validation.ts — Next 클릭 gating용 sub-step별 필수 입력 검증.
 *
 * Spec #18: Next 누를 때만 missing-input dialog 띄우기. Sidebar 클릭은 자유.
 * WizardContainer.validateBeforeNext에 연결되어 missing 항목을 i18n key 배열로 반환한다.
 */
import type { AppState } from "@/store/types";

export type KuroSubStepId =
  | "design.load"
  | "design.mutation"
  | "design.params"
  | "design.submit"
  | "output.summary"
  | "export.all";

export interface ValidationResult {
  ok: boolean;
  missing: string[];
}

export function validateForNext(
  sub: KuroSubStepId,
  state: AppState,
): ValidationResult {
  switch (sub) {
    case "design.load": {
      if (!state.seqInfo) {
        return { ok: false, missing: ["validation.missing.sequence"] };
      }
      return { ok: true, missing: [] };
    }
    case "design.mutation": {
      const text = state.mutationText?.trim() ?? "";
      const evolveCount = state.evolveproTotalCount ?? 0;
      if (text.length === 0 && evolveCount === 0) {
        return { ok: false, missing: ["validation.missing.mutation"] };
      }
      return { ok: true, missing: [] };
    }
    case "design.params":
    case "design.submit":
    case "output.summary":
    case "export.all":
    default:
      return { ok: true, missing: [] };
  }
}
