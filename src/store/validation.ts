/**
 * validation.ts — Next 클릭 및 action 버튼 클릭 gating용 필수 입력 검증.
 *
 * Spec #18: Next 누를 때만 missing-input dialog 띄우기. Sidebar 클릭은 자유.
 * WizardContainer.validateBeforeNext에 연결되어 missing 항목을 i18n key 배열로 반환한다.
 *
 * Item 2 (PI 2026-05-15): 작동 버튼(Generate barcode package, Merge,
 * Export all 등) 클릭 시에도 필수 입력 누락이면 경고. 액션별 validator는
 * `validateAction()`이 담당하며, 호출부는 toast.warning으로 missing[]을 안내한다.
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

// ---------------------------------------------------------------------------
// Action-button validators (Item 2)
// ---------------------------------------------------------------------------

/** ExportFormatSelector "Export all" button. PI: plate name now required. */
export interface ExportAllInput {
  fwdPlate: string;
  rvsPlate: string;
  wellCount: number;
  plateNameRe: RegExp;
}

export function validateExportAll(inp: ExportAllInput): ValidationResult {
  const missing: string[] = [];
  if (inp.fwdPlate.trim() === "") {
    missing.push("validation.missing.fwdPlateName");
  } else if (!inp.plateNameRe.test(inp.fwdPlate)) {
    missing.push("validation.missing.fwdPlateNameInvalid");
  }
  if (inp.rvsPlate.trim() === "") {
    missing.push("validation.missing.rvsPlateName");
  } else if (!inp.plateNameRe.test(inp.rvsPlate)) {
    missing.push("validation.missing.rvsPlateNameInvalid");
  }
  if (inp.wellCount <= 0) {
    missing.push("validation.missing.designResults");
  }
  return { ok: missing.length === 0, missing };
}

/** BarcodeSetupPanel "Generate barcode package" button. */
export interface GenerateBarcodePackageInput {
  fastaPath: string;
  barcodeSeedsPath: string;
  geneStart: string;
  geneEnd: string;
  isRangeValid: boolean;
  projectPath: string | null | undefined;
}

export function validateGenerateBarcodePackage(
  inp: GenerateBarcodePackageInput,
): ValidationResult {
  const missing: string[] = [];
  if (!inp.fastaPath) missing.push("validation.missing.cdsFasta");
  if (!inp.barcodeSeedsPath) missing.push("validation.missing.barcodeSeeds");
  if (inp.geneStart === "" || inp.geneEnd === "") {
    missing.push("validation.missing.geneCoordinates");
  } else if (!inp.isRangeValid) {
    missing.push("validation.missing.geneRangeInvalid");
  }
  if (!inp.projectPath) missing.push("validation.missing.projectPath");
  return { ok: missing.length === 0, missing };
}

/** ActivityPanel Merge buttons + Export Evolvepro xlsx button. */
export interface MergeActivityInput {
  activeRoundId: string | null | undefined;
  hasActivity: boolean;
}

export function validateMergeActivity(inp: MergeActivityInput): ValidationResult {
  const missing: string[] = [];
  if (!inp.activeRoundId) missing.push("validation.missing.activeRound");
  if (!inp.hasActivity) missing.push("validation.missing.activityData");
  return { ok: missing.length === 0, missing };
}
