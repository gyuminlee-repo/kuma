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

/**
 * 설계 엔진이 실제로 읽는 것. `designSlice.designPrimers` 는 mutationText 만
 * 보고 비어 있으면 "No mutations entered" 로 되돌아간다(designSlice.ts:179,
 * :185). 그래서 이것이 "실행 가능" 의 기준이다.
 */
function hasTypedMutations(state: AppState): boolean {
  return (state.mutationText?.trim() ?? "").length > 0;
}

/**
 * variant 출처가 잡혔는가. mutationText 가 있거나, EVOLVEpro pool 이 올라와 있어
 * 뒤이은 선택이 mutationText 를 채울 참이면 참이다.
 *
 * 이것이 "다음 단계로 넘어가도 되는가" 의 기준이고, 위 `hasTypedMutations` 가
 * "지금 돌려도 되는가" 의 기준이다. 둘의 차이는 여기 한 곳에만 있다. 실행 게이트
 * 가 이 판정을 다시 적으면(예전 useRunDesign 이 그랬다) 마법사는 넘어가는데 Run
 * Design 은 막힌 채 아무 말도 안 하는 상태가 생긴다.
 */
function hasVariantSource(state: AppState): boolean {
  return hasTypedMutations(state) || (state.evolveproTotalCount ?? 0) > 0;
}

/**
 * Run Design 게이트. `validateForNext` 와 같은 판정을 공유하되, 실행에만 필요한
 * 조건을 더한다. 반환값은 i18n 키이며 호출부가 번역한다.
 *
 * - 서열: design.load 와 같은 조건.
 * - mutations: 넘어가기는 pool 로 충분해도 실행은 mutationText 를 요구한다.
 * - 대상 유전자: 서열에 유전자가 여럿이면 어느 것인지 정해져야 설계가 성립한다.
 *   마법사에는 이 단계가 따로 없어 실행 게이트에만 있다.
 */
export function validateForRun(state: AppState): ValidationResult {
  const missing: string[] = [];
  if (!state.seqInfo) missing.push("appLayout.missingSeqFile");
  if (!hasTypedMutations(state)) missing.push("appLayout.missingMutations");
  if (state.seqInfo && state.seqInfo.genes.length > 1 && !state.selectedGene) {
    missing.push("appLayout.missingTargetGene");
  }
  return { ok: missing.length === 0, missing };
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
      if (!hasVariantSource(state)) {
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
  geneName: string;
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
  if (!inp.geneName.trim()) missing.push("mame.barcodeSetup.geneName");
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
