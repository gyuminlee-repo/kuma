/**
 * useAutosaveHydration.ts — Phase 4: 프로젝트 진입 시 자동 저장 파일 복원
 *
 * 프로젝트가 처음 활성화될 때 한 번만 실행된다.
 * kuro와 mame 두 스냅샷을 병렬로 읽고 각 store에 복원한다.
 * KURO는 schema 2부터 결과물 필드(designResults 등)까지 함께 복원한다.
 * MAME 결과물은 별도 result 스냅샷 경로(restoreMameResult)로 복원한다.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import i18next from "i18next";
import { useKumaProject } from "@/state/projectContext";
import {
  readAutosave,
  readScratchAutosave,
  deleteScratchAutosave,
  blockAutosaveWrites,
  clearAutosaveBlock,
  beginHydration,
  endHydration,
  ensureAutosaveDir,
  autosavePath,
  atomicWriteJson,
} from "@/lib/autosave";
import { readMameResultSnapshot } from "@/lib/mame/resultSnapshot";
import { pickAnalyzeYield } from "@/lib/mame/analyzeYield";
import { sendRequest as sendMameRequest } from "@/lib/ipc-mame";
import type { LoadAnalyzeResultResponse, PlateOrderReport } from "@/types/mame/models";
import {
  buildPlateOrderMessage,
  isPlateOrderReportable,
} from "@/lib/mame/plateOrderMessage";
import { KURO_SCHEMA, buildKuroSnapshot } from "@/lib/kuroSnapshot";
import { buildKuroResultResetPatch } from "@/lib/kuroResultReset";
import { fingerprintSource, fingerprintsEqual, type SourceFingerprint } from "@/lib/sourceFingerprint";
import { MAJOR_ORDER, SUBSTEP_ORDER, type MajorStepId, type StepStatus, type SubStepId } from "@/store/slices/navigationSlice";
import { MAME_SCHEMA } from "@/lib/mame/autosaveSnapshot";
import { detectProjectFiles, detectFromInputDir } from "@/lib/mame/detectProjectFiles";
import {
  basename as inputBasename,
  useMissingInputs,
  type MissingInput,
} from "@/lib/mame/missingInputs";
import {
  findStaleMamePaths,
  MAME_PATH_LABEL_KEYS,
  type MamePathField,
} from "@/lib/mame/stalePaths";
import { exists } from "@tauri-apps/plugin-fs";
import { getLatestArtifact, openWorkspace } from "@/lib/workspace";
import { resolvePolymeraseName, retiredPolymeraseNotice } from "@/lib/polymeraseAliases";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { resetMameAll } from "@/store/mame/resetAll";
import { useRoundStore } from "@/store/round/roundSlice";
import type { AppState } from "@/store/appStore";
import type { AppState as MameAppState } from "@/store/mame/types";
import type { RawRunParams } from "@/store/mame/slice-interfaces";
import type { AutosaveSnapshot, ReadAutosaveResult } from "@/lib/autosave";
import type { MameAutosaveSnapshot } from "@/lib/mame/autosaveSnapshot";
import { fromPortablePath, isExternalPath } from "@/lib/projectPath";

// ─── 공개 타입 ────────────────────────────────────────────────────────────

export interface HydrationStatusMessage {
  kind: "kuro" | "mame";
  variant:
    | "restored"
    | "corrupted"
    | "schema_too_new"
    | "missing"
    | "io_failed"
    /** 복원된 결과물이 재선택된 variant 목록과 어긋나 폐기됐다. */
    | "results_discarded"
    /**
     * 스냅샷이 가리키는 입력 파일을 열지 못했다. 프로젝트 폴더를 다른 PC로 옮겼고
     * 그 입력이 폴더 밖에 있었을 때 주로 발생한다. 조용히 넘기면 결과물만 복원되고
     * 그 근거가 된 입력은 빠진 상태가 되므로 반드시 사용자에게 알린다.
     */
    | "inputs_unavailable"
    /**
     * 복원한 expected 워크북이 자기 자신과 어긋난다. `expected_mutations` 순서가 같은
     * 파일의 프라이머 플레이트 시트와 다르면 MAME 는 행 번호로 well 을 세므로 전 well
     * 이 잘못된 설계로 채점된다. 숫자만 보면 정상으로 보이는 종류라 반드시 알린다.
     */
    | "plate_order_mismatch";
  message: string;
  /** ISO 문자열. "5분 전" 표시용 */
  savedAt?: string;
}

/**
 * 복원 진행 단계. 오버레이가 읽는 진행 정보의 단일 채널이다.
 *
 * 호출부의 범용 상태바를 빌려 쓰지 않는다. 그 상태바는 4초 자동 소멸이고, 주
 * 복원 메시지(variant "restored")는 자동 저장 인디케이터 라벨로만 흘러 진행
 * 영역이 한 번도 렌더되지 않았다. 진행 표시는 훅이 직접 노출하는 편이 옳다.
 *
 * 다섯 값이 모든 복원에서 나오지는 않는다. scratch 복원은 "reset"과 "kuro"만
 * 거친다. "workspace"·"mame"·"detect"는 워크스페이스 레지스트리·MAME 복원·자동
 * 탐지 구간이고 셋 다 프로젝트 전용이라 scratch 경로에서는 도달하지 않는다.
 * 표시를 고정 단계 수 진행률로 만들면 scratch에서 중간에 멈춘 것처럼 보인다.
 */
export type HydrationPhase = "reset" | "workspace" | "kuro" | "mame" | "detect";

/** useAutosaveHydration 반환값. 호출부가 복원 구간을 차단 UI로 덮는 데 쓴다. */
export interface AutosaveHydrationHandle {
  /** 복원이 진행 중이면 true. 조기 return 경로에서는 true가 되지 않는다. */
  hydrating: boolean;
  /**
   * 현재 복원 단계. 복원 중이 아니면 null이고, 조기 return 경로에서는 null로
   * 남는다. 취소·정상 종료 어느 쪽으로 끝나든 hydrating과 같은 지점에서 null로
   * 되돌아간다.
   */
  phase: HydrationPhase | null;
  /**
   * 진행 중인 복원의 후속 적용을 중단한다. 아래 6가지가 이 함수의 실제 계약이다.
   *
   * 1. 이미 떠난 사이드카 RPC(loadSequence, loadEvolveproCsv,
   *    load_analyze_result)는 중단되지 않는다. 요청은 그대로 완주한다.
   * 2. KURO 스냅샷 적용은 applyKuroSnapshot에 넘긴 isCurrent 가드로 실제
   *    중단된다. 다만 그 가드가 막는 것은 가드 지점 이후다. setState(patch),
   *    variant 발산 판정, setSubStep은 멈추지만, 취소 시점에 이미 떠난
   *    loadSequence·loadEvolveproCsv의 store 쓰기(seqInfo, mutationText)는
   *    그대로 착지한다.
   * 3. restoreMameResult·applyMameAutoDetect·promoteScratchToProject도 같은
   *    isCurrent 가드를 받는다. MAME store 쓰기, 사이드카 호출, scratch 승격은
   *    각 쓰기 statement 직전에 끊긴다. (1)과 마찬가지로 이미 떠난 요청의 응답은
   *    버려질 뿐 취소되지는 않는다.
   * 4. 자동 저장 게이트(hydrationDepth)는 cancel()이 즉시 푼다. 고아가 된 IIFE의
   *    finally를 기다리지 않는다. 언마운트와 프로젝트 전환도 같은 시점에 푼다.
   *    run당 gateReleased 래치가 하나라서 어느 쪽이 먼저 도착하든 endHydration은
   *    정확히 한 번만 불린다.
   * 5. hydrating과 phase는 즉시 내려간다(false, null). 뒤늦게 도착하는 고아 run의
   *    finally는 activeRunRef가 이미 바뀌어 있어 이 값을 되돌리지 못한다.
   * 6. 화면 전환은 호출부 책임이다. cancel()은 lastHydratedKey를 건드리지 않는다.
   *    정상 재진입(kuma:return-to-home → MainShell 언마운트 → 재진입)은 언마운트
   *    effect가 키를 비우므로 새 ref로 복원되고, 마운트를 유지한 채 같은 키로
   *    effect가 재실행되는 경우는 dup-key 가드에 걸려 skip된다.
   */
  cancel: () => void;
}

/** applyKuroSnapshot 결과. 호출부가 사용자 알림을 결정하는 데 쓴다. */
export interface KuroSnapshotApplyOutcome {
  /** 재선택된 variant 목록과 어긋나 복원된 결과물을 폐기했으면 true. */
  resultsDiscarded: boolean;
  /**
   * 열지 못한 입력 파일 경로. 비어 있으면 전부 정상이다. 복원 자체는 계속하되
   * 호출부가 사용자에게 알린다. 결과물은 살아 있는데 근거 입력이 빠진 상태를
   * 조용히 두면 어긋난 화면을 정상으로 오인한다.
   */
  unavailableInputs: string[];
}

// ─── 상대 시간 포맷 헬퍼 ─────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return i18next.t("autosaveHydration.relativeJustNow");
  if (diffMin < 60) return i18next.t("autosaveHydration.relativeMinAgo", { count: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return i18next.t("autosaveHydration.relativeHrAgo", { count: diffHr });
  return i18next.t("autosaveHydration.relativeDayAgo", { count: Math.floor(diffHr / 24) });
}

// ─── Kuro 복원 ────────────────────────────────────────────────────────────

function isMutationInputMode(value: unknown): value is AppState["mutationInputMode"] {
  return value === "text" || value === "evolvepro";
}

/** Accepts the legacy "others" literal too, callers coerce it to "pipeline". */
function isEvolveproModeRaw(value: unknown): value is "topN" | "pipeline" | "others" {
  return value === "topN" || value === "pipeline" || value === "others";
}

function isScoreOrder(value: unknown): value is "asc" | "desc" {
  return value === "asc" || value === "desc";
}

function isCodonStrategy(value: unknown): value is AppState["codonStrategy"] {
  return value === "closest" || value === "optimal";
}

function isOverlapMode(value: unknown): value is AppState["overlapMode"] {
  return value === "partial" || value === "full";
}

function isDomainStrategy(value: unknown): value is AppState["domainStrategy"] {
  return value === "proportional" || value === "equal";
}

function isDomainOverlapPolicy(value: unknown): value is AppState["domainOverlapPolicy"] {
  return value === "first" || value === "largest";
}

function isLinkerHandling(value: unknown): value is AppState["linkerHandling"] {
  return value === "include" || value === "separate-bin" || value === "exclude";
}

function isDistanceMode(value: unknown): value is AppState["distanceMode"] {
  return value === "auto" || value === "1d" || value === "3d";
}

function isMajorStepId(value: unknown): value is MajorStepId {
  return typeof value === "string" && (MAJOR_ORDER as string[]).includes(value);
}

function isSubStepId(value: unknown): value is SubStepId {
  if (typeof value !== "string") return false;
  return Object.values(SUBSTEP_ORDER).some((steps) => (steps as string[]).includes(value));
}

/**
 * 스냅샷의 stepStatus를 현재 스키마의 전체 sub-step 키 집합에 병합한다.
 *
 * 저장 시점 이후 새 sub-step이 추가됐을 수 있어(스키마 자체 확장), 저장값을
 * 그대로 덮어쓰면 새 키가 빠진 채 stepStatus가 부분적으로만 존재하게 된다.
 * navigationSlice.buildInitialStepStatus와 동일한 기본값 위에 저장값 중
 * 유효한 키만 얹는다.
 */
function mergeStepStatus(saved: unknown): Record<SubStepId, StepStatus> {
  const base: Record<SubStepId, StepStatus> = {} as Record<SubStepId, StepStatus>;
  for (const steps of Object.values(SUBSTEP_ORDER)) {
    for (const id of steps) {
      base[id] = { done: false, reachable: true };
    }
  }
  if (typeof saved !== "object" || saved === null) return base;
  for (const [key, value] of Object.entries(saved as Record<string, unknown>)) {
    if (!isSubStepId(key)) continue;
    if (typeof value !== "object" || value === null) continue;
    const candidate = value as Record<string, unknown>;
    if (typeof candidate.done === "boolean" && typeof candidate.reachable === "boolean") {
      base[key] = { done: candidate.done, reachable: candidate.reachable };
    }
  }
  return base;
}

function isSourceFingerprint(value: unknown): value is SourceFingerprint {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.size === "number" && typeof candidate.mtimeMs === "number";
}

/**
 * 재도출 결과에 영향을 주는 설정 필드. 값이 하나라도 patch에 실리지 않았으면
 * (스냅샷에 해당 필드가 없거나 타입 가드에서 걸러진 경우) 재도출 폴백으로
 * 안전하게 떨어뜨린다.
 *
 * 정상 복원 경로에서는 이 값들이 모두 같은 스냅샷의 diversity/parameters
 * 블록에서 나와 patch에 항상 실린다(자동 저장 복원은 저장 당시 설정을 그대로
 * 복원한다). 이 목록은 그 전제가 깨졌는지 확인하는 방어용이며, "현재 설정과
 * 재도출 설정이 실제로 다른가"를 새로 계산하지는 않는다(같은 patch에서 나온
 * 값끼리는 항등이라 계산할 것이 없다).
 */
// 역할: loadEvolveproCsv 빠른 경로(재도출 건너뛰기) 진입 전, 저장 당시
// 파라미터가 지금 patch에 그대로 실렸는지 확인하는 방어 게이트다.
const REDESIGN_SENSITIVE_PARAM_KEYS: ReadonlyArray<keyof AppState> = [
  "evolveproMode",
  "roundSize",
  "evolveproRound",
  "maxPrimers",
  "positionDiversityEnabled",
  "maxPerPosition",
  "domainDiversityEnabled",
  "domainStrategy",
  "domainOverlapPolicy",
  "linkerHandling",
  "domainQuotaMin",
  "paretoDiversityEnabled",
  "entropyWeightEnabled",
  "entropyWeight",
  "paretoPoolMultiplier",
  "distanceMode",
  "structuralDiversityEnabled",
  "structuralKappa",
];

function pipelineParamsAppliedToPatch(patch: Partial<AppState>): boolean {
  return REDESIGN_SENSITIVE_PARAM_KEYS.every((key) => key in patch);
}

/**
 * mutationText를 divergence 비교용으로 토큰화한다.
 * prepareDesignInput(designSlice.helpers.ts)의 토큰화와 동일하게 맞춘다.
 */
function tokenizeMutationText(text: string): Set<string> {
  return new Set(
    text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#")),
  );
}

/**
 * 저장 시점 입력이 재도출 입력과 달라졌으면 복원된 결과물을 비운다.
 *
 * loadEvolveproCsv는 source 파일을 다시 읽어 mutationText를 새 variant 목록으로
 * 덮어쓴다(inputSlice.helpers.ts buildEvolveproLoadStateUpdate). CSV가 편집됐거나
 * round/quota 설정이 달라졌으면 그 목록이 스냅샷 저장 시점과 달라지고, 표에는 옛
 * 프라이머가 목록에는 새 변이가 남는 조용한 불일치가 생긴다. 조용히 유지하는 대신
 * 결과물을 비우고 호출부가 사용자에게 알리게 한다.
 *
 * 비교 대상: 저장 시점 스냅샷의 mutation_text와 재도출 후 현재 mutationText를
 * 줄 단위 토큰화해 **집합 동일성**으로 비교한다(순서 차이로 오발화하지 않게).
 * designResults의 mutation 라벨을 (mutationText ∪ poolVariants)의 부분집합인지
 * 보는 이전 방식은 폐기했다. fill-on-failure/rescue로 poolVariants에서 채워진
 * 결과의 mutation은 애초에 mutationText에 없는 게 정상이라, 그 방식은 정상
 * 상태에서도 늘 발산으로 오판했다(designResults 95건 저장 → 복원 시 71건이
 * mutationText 밖 pool 유래라 전량 폐기되는 실사례). "무엇이 달라졌는가"를
 * 직접 보는 이 방식은 그 오판을 없앤다.
 *
 * 스냅샷에 mutation_text가 없거나 문자열이 아니면(schema 3 이하 구 스냅샷)
 * 비교 근거가 없으므로 판정을 건너뛰고 결과를 유지한다(근거 없이 지우지 않는다).
 *
 * 재설계까지 돌리지는 않는다. restoreWorkspace(autoRedesignOnLoad)는 사용자가
 * 명시적으로 연 워크스페이스라 재설계가 정당하지만, 자동 저장 복원은 앱 진입
 * 경로여서 사이드카 설계 작업을 자동으로 띄우는 건 과하다.
 */
function discardResultsIfVariantsDiverged(savedMutationText: unknown): boolean {
  const state = useAppStore.getState();
  if (state.designResults.length === 0) return false;
  if (typeof savedMutationText !== "string") return false;

  const saved = tokenizeMutationText(savedMutationText);
  const current = tokenizeMutationText(state.mutationText);
  const diverged =
    saved.size !== current.size || [...saved].some((line) => !current.has(line));
  if (!diverged) return false;

  // 결과물 블록을 한 번에 비운다. 스냅샷 results 블록이 채우는 필드와 1:1로
  // 맞춰야 표와 카운터가 어긋나지 않는다. 필드 목록은 sequenceSlice의 템플릿 변경
  // 무효화와 공유한다(lib/kuroResultReset.ts).
  useAppStore.setState(buildKuroResultResetPatch());
  return true;
}

/**
 * Exported for unit testing (legacy "others" -> "pipeline" migration path).
 *
 * `isCurrent`를 주면 store를 쓰는 statement 직전마다 취소 여부를 재확인하고,
 * 취소됐으면 그 지점에서 즉시 빠진다. 사후 검사로는 막을 수 없다. loadSequence·
 * loadEvolveproCsv·discardResultsIfVariantsDiverged 자체가 store 쓰기라, 취소한
 * A의 in-flight 스냅샷이 B의 resetAll 뒤에 착지하면 B의 designResults·
 * mutationText·plateMappings가 A의 값으로 오염되고 B에서 한 번만 편집해도 B의
 * kuro.json에 영구화된다. 인자를 생략하면 항상 진행한다(단위 테스트 경로).
 */
export async function applyKuroSnapshot(
  snapshot: AutosaveSnapshot,
  isCurrent?: () => boolean,
  projectPath: string | null = null,
): Promise<KuroSnapshotApplyOutcome> {
  const alive = () => isCurrent?.() ?? true;
  // 열지 못한 입력을 모아 호출부가 한 번에 알리도록 한다.
  const unavailableInputs: string[] = [];
  const done = (resultsDiscarded: boolean): KuroSnapshotApplyOutcome => ({
    resultsDiscarded,
    unavailableInputs,
  });
  // schema 3+ 스냅샷의 `project://` 경로를 현재 프로젝트 폴더 기준 절대 경로로
  // 되돌린다. 구 스냅샷의 절대 경로는 그대로 통과한다.
  const resolve = (value: string): string => fromPortablePath(projectPath, value);
  const input = snapshot.input as Record<string, unknown> | undefined;
  const params = snapshot.parameters as Record<string, unknown> | undefined;
  const diversity = snapshot.diversity as Record<string, unknown> | undefined;
  const patch: Partial<AppState> = {};

  // input
  if (isMutationInputMode(input?.mutation_input_mode)) {
    // Coerce legacy "text" mode to "evolvepro" (Text input removed from UI)
    patch.mutationInputMode = input.mutation_input_mode === "text" ? "evolvepro" : input.mutation_input_mode;
  }
  if (typeof input?.mutation_text === "string") {
    patch.mutationText = input.mutation_text;
  }
  if (input?.sequence_path === null) {
    patch.fastaPath = "";
    patch.seqInfo = null;
    patch.selectedGene = "";
  }
  if (typeof input?.organism === "string") {
    patch.organism = input.organism;
  }
  if (isEvolveproModeRaw(input?.evolvepro_mode)) {
    // Legacy "others" (pre-merge autosaves) coerces to "pipeline", the
    // "Others" source file is now loaded through evolveproCsvPath with
    // column-mapping overrides, not a separate mode.
    patch.evolveproMode = input.evolvepro_mode === "others" ? "pipeline" : input.evolvepro_mode;
  } else if (typeof diversity?.pipeline_mode === "boolean") {
    patch.evolveproMode = diversity.pipeline_mode ? "pipeline" : "topN";
  }
  // Legacy fallback: pre-merge autosaves wrote both evolvepro_* (real value
  // only when mode !== "others") and others_* (real value only when mode
  // === "others") unconditionally. Pick the channel that was actually
  // authoritative for the saved mode so an untouched default on the inactive
  // channel never clobbers the real override.
  const wasOthersMode = input?.evolvepro_mode === "others";
  if (wasOthersMode) {
    if (typeof input?.others_source_path === "string" || input?.others_source_path === null) {
      patch.evolveproCsvPath = input.others_source_path
        ? resolve(input.others_source_path)
        : "";
    }
    if (typeof input?.others_variant_column === "string" || input?.others_variant_column === null) {
      patch.evolveproVariantColumn = input.others_variant_column;
    }
    if (typeof input?.others_score_column === "string" || input?.others_score_column === null) {
      patch.evolveproScoreColumn = input.others_score_column;
    }
    if (isScoreOrder(input?.others_score_order)) {
      patch.evolveproScoreOrder = input.others_score_order;
    }
    if (typeof input?.others_sheet_name === "string" || input?.others_sheet_name === null) {
      patch.evolveproSheetName = input.others_sheet_name;
    }
  } else {
    if (typeof input?.evolvepro_csv_path === "string" || input?.evolvepro_csv_path === null) {
      patch.evolveproCsvPath = input.evolvepro_csv_path
        ? resolve(input.evolvepro_csv_path)
        : "";
    }
    if (typeof input?.evolvepro_variant_column === "string" || input?.evolvepro_variant_column === null) {
      patch.evolveproVariantColumn = input.evolvepro_variant_column;
    }
    if (typeof input?.evolvepro_score_column === "string" || input?.evolvepro_score_column === null) {
      patch.evolveproScoreColumn = input.evolvepro_score_column;
    }
    if (isScoreOrder(input?.evolvepro_score_order)) {
      patch.evolveproScoreOrder = input.evolvepro_score_order;
    }
    if (typeof input?.evolvepro_sheet_name === "string" || input?.evolvepro_sheet_name === null) {
      patch.evolveproSheetName = input.evolvepro_sheet_name;
    }
  }

  // parameters
  if (typeof params?.polymerase === "string") {
    // Retired profiles are remapped here rather than via setSelectedPolymerase,
    // so the snapshot GC range and overlap mode restored below are preserved.
    const { name, retiredFrom } = resolvePolymeraseName(params.polymerase);
    patch.selectedPolymerase = name;
    if (retiredFrom) {
      patch.statusMessage = retiredPolymeraseNotice(
        retiredFrom,
        name,
        typeof params?.gc_min === "number" ? params.gc_min : useAppStore.getState().gcMin,
        typeof params?.gc_max === "number" ? params.gc_max : useAppStore.getState().gcMax,
      );
    }
  }
  if (isCodonStrategy(params?.codon_strategy)) {
    patch.codonStrategy = params.codon_strategy;
  }
  if (typeof params?.max_primers === "number") {
    patch.maxPrimers = params.max_primers;
  }
  if (typeof params?.tm_fwd_target === "number") {
    patch.tmFwdTarget = params.tm_fwd_target;
  }
  if (typeof params?.tm_rev_target === "number") {
    patch.tmRevTarget = params.tm_rev_target;
  }
  if (typeof params?.tm_overlap_target === "number") {
    patch.tmOverlapTarget = params.tm_overlap_target;
  }
  if (typeof params?.gc_min === "number") {
    patch.gcMin = params.gc_min;
  }
  if (typeof params?.gc_max === "number") {
    patch.gcMax = params.gc_max;
  }
  if (typeof params?.primer_len_enabled === "boolean") {
    patch.primerLenEnabled = params.primer_len_enabled;
  }
  if (typeof params?.fwd_len_min === "number") {
    patch.fwdLenMin = params.fwd_len_min;
  }
  if (typeof params?.fwd_len_max === "number") {
    patch.fwdLenMax = params.fwd_len_max;
  }
  if (typeof params?.rev_len_min === "number") {
    patch.revLenMin = params.rev_len_min;
  }
  if (typeof params?.rev_len_max === "number") {
    patch.revLenMax = params.rev_len_max;
  }
  if (typeof params?.fill_on_failure === "boolean") {
    patch.fillOnFailure = params.fill_on_failure;
  }
  if (isOverlapMode(params?.overlap_mode)) {
    patch.overlapMode = params.overlap_mode;
  }

  // diversity
  if (Array.isArray(diversity?.domains) && Array.isArray(diversity?.disabled_domains)) {
    patch.domains = diversity.domains as AppState["domains"];
    patch.disabledDomains = diversity.disabled_domains as string[];
  }
  if (typeof diversity?.position_diversity_enabled === "boolean") {
    patch.positionDiversityEnabled = diversity.position_diversity_enabled;
  }
  if (typeof diversity?.max_per_position === "number") {
    patch.maxPerPosition = diversity.max_per_position;
  }
  if (typeof diversity?.domain_diversity_enabled === "boolean") {
    patch.domainDiversityEnabled = diversity.domain_diversity_enabled;
  }
  if (isDomainStrategy(diversity?.domain_strategy)) {
    patch.domainStrategy = diversity.domain_strategy;
  }
  if (isDomainOverlapPolicy(diversity?.domain_overlap_policy)) {
    patch.domainOverlapPolicy = diversity.domain_overlap_policy;
  }
  if (isLinkerHandling(diversity?.linker_handling)) {
    patch.linkerHandling = diversity.linker_handling;
  }
  if (typeof diversity?.domain_quota_min === "number") {
    patch.domainQuotaMin = diversity.domain_quota_min;
  }
  if (typeof input?.uniprot_accession === "string" || input?.uniprot_accession === null) {
    patch.uniprotAccession = input.uniprot_accession ?? "";
  }
  if (typeof diversity?.pareto_diversity_enabled === "boolean") {
    patch.paretoDiversityEnabled = diversity.pareto_diversity_enabled;
  }
  if (typeof diversity?.structural_diversity_enabled === "boolean") {
    patch.structuralDiversityEnabled = diversity.structural_diversity_enabled;
  }
  if (typeof diversity?.structural_kappa === "number") {
    patch.structuralKappa = Math.max(0, Math.min(1, diversity.structural_kappa));
  }
  if (typeof diversity?.entropy_weight_enabled === "boolean") {
    patch.entropyWeightEnabled = diversity.entropy_weight_enabled;
  }
  if (typeof diversity?.entropy_weight === "number") {
    patch.entropyWeight = diversity.entropy_weight;
  }
  if (typeof diversity?.pareto_pool_multiplier === "number") {
    patch.paretoPoolMultiplier = diversity.pareto_pool_multiplier;
  }
  if (isDistanceMode(diversity?.distance_mode)) {
    patch.distanceMode = diversity.distance_mode;
  }
  if (typeof diversity?.evolvepro_round === "number") {
    patch.evolveproRound = diversity.evolvepro_round;
  }
  if (typeof diversity?.round_size === "number") {
    patch.roundSize = diversity.round_size;
  }
  if (typeof diversity?.auto_redesign_on_load === "boolean") {
    patch.autoRedesignOnLoad = diversity.auto_redesign_on_load;
  }
  if (typeof diversity?.save_cache === "boolean") {
    patch.saveCache = diversity.save_cache;
  }
  // schema 5+. exportSlice의 settings 블록과 같은 이유로 saveCache와 무관하게
  // 항상 복원한다(위 kuroSnapshot.ts diversity 블록 주석 참조).
  if (Array.isArray(diversity?.ref_domains)) {
    patch.refDomains = diversity.ref_domains as AppState["refDomains"];
  }
  if (typeof diversity?.ref_domain_hash === "string") {
    patch.refDomainHash = diversity.ref_domain_hash;
  }
  if (typeof diversity?.structure_accession === "string") {
    patch.structureAccession = diversity.structure_accession;
  }
  if (typeof diversity?.structure_loaded === "boolean") {
    patch.structureLoaded = diversity.structure_loaded;
  }
  // schema 5+. 지문 일치로 loadSequence를 건너뛰면(아래 (a)) 그게 띄우던
  // fire-and-forget searchUniprot도 안 돌아 uniprotCandidates를 재생성할 길이
  // 없다. 구 스냅샷에는 이 필드가 없으므로 Array.isArray 가드로만 덮어쓴다
  // (없으면 건드리지 않는다, 근거 없이 빈 배열로 지우지 않는다).
  if (Array.isArray(diversity?.uniprot_candidates)) {
    patch.uniprotCandidates = diversity.uniprot_candidates as AppState["uniprotCandidates"];
  }

  // parameters 확장 (schema 5+)
  if (typeof params?.tm_tolerance === "number") {
    patch.tmTolerance = params.tm_tolerance;
  }
  if (typeof params?.random_seed === "number" || params?.random_seed === null) {
    patch.randomSeed = params.random_seed ?? null;
  }

  // benchmark (schema 5+)
  const benchmark = snapshot.benchmark as Record<string, unknown> | undefined;
  if (typeof benchmark?.benchmark_top_percentile === "number") {
    patch.benchmarkTopPercentile = benchmark.benchmark_top_percentile;
  }
  if (typeof benchmark?.benchmark_random_trials === "number") {
    patch.benchmarkRandomTrials = benchmark.benchmark_random_trials;
  }
  if (typeof benchmark?.benchmark_random_seed === "number" || benchmark?.benchmark_random_seed === null) {
    patch.benchmarkRandomSeed = benchmark?.benchmark_random_seed ?? null;
  }

  // ui (schema 5+)
  const ui = snapshot.ui as Record<string, unknown> | undefined;
  if (Array.isArray(ui?.table_sorting)) {
    patch.tableSorting = ui.table_sorting as AppState["tableSorting"];
  }

  // sources (schema 5+). loadSequence/loadEvolveproCsv 재도출을 건너뛸 수 있는지
  // 판정하는 근거. 아래 (a)/(d) 각각에서 쓴다.
  const sources = snapshot.sources as Record<string, unknown> | undefined;
  const savedSequenceFingerprint = isSourceFingerprint(sources?.sequence_fingerprint)
    ? sources.sequence_fingerprint
    : null;
  const savedEvolveproCsvFingerprint = isSourceFingerprint(sources?.evolvepro_csv_fingerprint)
    ? sources.evolvepro_csv_fingerprint
    : null;
  const savedSequenceInfo =
    typeof input?.sequence_info === "object" && input.sequence_info !== null
      ? (input.sequence_info as AppState["seqInfo"])
      : null;
  const pipeline = snapshot.pipeline as Record<string, unknown> | undefined;

  // (a) loadSequence는 그 자체가 store 쓰기라 호출 전에 막아야 한다.
  if (!alive()) return done(false);
  if (typeof input?.sequence_path === "string" && input.sequence_path) {
    const sequencePath = resolve(input.sequence_path);
    if (!sequencePath) {
      unavailableInputs.push(input.sequence_path);
    } else {
      // 지문이 일치하고 seqInfo 원본이 있으면 loadSequence를 다시 돌리지
      // 않는다. loadSequence는 domains/refDomains/poolVariants 등을 초기화하고
      // searchUniprot/annotateReferenceDomains를 fire-and-forget으로 띄우는
      // 부수효과가 있어, 그 결과가 이 복원이 붓는 patch보다 늦게 착지하며
      // 방금 복원한 값을 덮어썼다(문제 2 배경 참조).
      const currentFingerprint = savedSequenceFingerprint && savedSequenceInfo
        ? await fingerprintSource(sequencePath)
        : null;
      if (!alive()) return done(false);
      if (
        savedSequenceFingerprint &&
        savedSequenceInfo &&
        fingerprintsEqual(savedSequenceFingerprint, currentFingerprint)
      ) {
        patch.fastaPath = sequencePath;
        patch.seqInfo = savedSequenceInfo;
        // loadSequence가 하던 MAME 공유 store dual-write를 대신 수행한다.
        try {
          useMameAppStore.getState().setSharedFastaPath(sequencePath);
        } catch {
          // Defensive: never let the cross-store hand-off break restore.
        }
      } else {
        try {
          await useAppStore.getState().loadSequence(sequencePath);
        } catch {
          // 복원은 계속하되 조용히 넘기지 않는다. 옮긴 프로젝트에서 폴더 밖
          // 서열 파일이 빠졌을 때 이 경로로 온다.
          console.warn("[autosave] kuro: sequence load failed, continuing restore");
          unavailableInputs.push(sequencePath);
        }
      }
    }
  }
  // (b) await 동안 취소됐을 수 있다. 이미 착지한 seqInfo는 되돌리지 못하지만
  //     뒤따르는 patch 조립·적용은 여기서 끊는다.
  if (!alive()) return done(false);

  const selectedCds = typeof input?.selected_cds === "string" ? input.selected_cds : "";
  if (selectedCds) {
    // 빠른 경로(지문 일치, loadSequence 재호출 생략)에서는 아직 store에 착지하지
    // 않았으므로 patch.seqInfo를 먼저 본다. 일반 경로는 loadSequence의 await가
    // 끝난 뒤라 store에 이미 반영돼 있어 기존과 동일하게 동작한다.
    const seqInfoForGeneCheck = patch.seqInfo ?? useAppStore.getState().seqInfo;
    const geneExists = seqInfoForGeneCheck?.genes.some((g) => String(g.cds_start) === selectedCds) ?? false;
    if (geneExists) {
      patch.selectedGene = selectedCds;
    }
  }

  // results (schema 2+). schema 1 스냅샷에는 results가 없으므로 결과물만 비어 있게 된다.
  const results = snapshot.results as Record<string, unknown> | undefined;
  if (results !== undefined) {
    if (Array.isArray(results.designResults)) {
      patch.designResults = results.designResults as AppState["designResults"];
      // 디스크에서 복원한 결과물은 사이드카 설계 상태와 무관하다.
      // 이 플래그가 true로 남으면 primer swap/alternatives가 없는 백엔드
      // 상태를 가정하고 동작한다.
      patch.backendDesignStateSynced = false;
    }
    if (typeof results.successCount === "number") {
      patch.successCount = results.successCount;
    }
    if (typeof results.totalCount === "number") {
      patch.totalCount = results.totalCount;
    }
    if (Array.isArray(results.failedMutations)) {
      patch.failedMutations = results.failedMutations as AppState["failedMutations"];
    }
    if (Array.isArray(results.plateMappings)) {
      patch.plateMappings = results.plateMappings as AppState["plateMappings"];
    }
    if (typeof results.dedupInfo === "object" && results.dedupInfo !== null) {
      patch.dedupInfo = results.dedupInfo as AppState["dedupInfo"];
    }
    if (typeof results.manuallySwapped === "object" && results.manuallySwapped !== null) {
      const safe: Record<string, "fwd" | "rev" | "both"> = {};
      for (const [k, v] of Object.entries(results.manuallySwapped)) {
        if (v === "fwd" || v === "rev" || v === "both") safe[k] = v;
      }
      patch.manuallySwapped = safe;
    }
    if (typeof results.customCandidates === "object" && results.customCandidates !== null) {
      patch.customCandidates = results.customCandidates as AppState["customCandidates"];
    }
    if (Array.isArray(results.rescuedMutationDetails)) {
      patch.rescuedMutationDetails = results.rescuedMutationDetails as AppState["rescuedMutationDetails"];
    }
    // schema 4+. schema 3 이하 스냅샷에는 없으므로 여기서는 그대로 둔다(하위
    // 호환). 뒤이은 loadEvolveproCsv(아래)가 재도출한 pool로 다시 덮어쓰는 것이
    // 정상이며, 여기서 복원하는 목적은 그 사이 divergence 판정에 값이 있게
    // 하는 것이 아니라 결과 화면이 poolVariants를 참조하는 다른 UI(예:
    // DiversityOptions 조합 비율)가 hydration 도중에도 빈 상태로 잠깐 깜빡이지
    // 않게 하는 것이다.
    if (Array.isArray(results.poolVariants)) {
      patch.poolVariants = results.poolVariants as AppState["poolVariants"];
    }
    // schema 5+. rescuedMutations/showBenchmark는 항상 저장되므로 항상 복원.
    // alternativesCache/benchmarkResults는 saveCache가 꺼져 있으면 스냅샷에
    // 없으므로(kuroSnapshot.ts 참조) 여기서는 있을 때만 덮어쓴다.
    if (Array.isArray(results.rescuedMutations)) {
      patch.rescuedMutations = results.rescuedMutations as AppState["rescuedMutations"];
    }
    if (typeof results.showBenchmark === "boolean") {
      patch.showBenchmark = results.showBenchmark;
    }
    if (typeof results.alternativesCache === "object" && results.alternativesCache !== null) {
      patch.alternativesCache = results.alternativesCache as AppState["alternativesCache"];
    }
    if (typeof results.benchmarkResults === "object" && results.benchmarkResults !== null) {
      patch.benchmarkResults = results.benchmarkResults as AppState["benchmarkResults"];
    }
  }

  // (c) 스냅샷 본체를 store에 붓는 지점. 취소된 복원의 patch가 다음 프로젝트
  //     store에 착지하는 것을 막는 핵심 가드다.
  if (!alive()) return done(false);
  useAppStore.setState(patch);

  let resultsDiscarded = false;
  const activeSourcePath = patch.evolveproCsvPath ?? useAppStore.getState().evolveproCsvPath;
  if (activeSourcePath) {
    // pipeline 블록이 재도출 없이 fast-path를 채울 만큼 온전한지. 지문이
    // 있어도 이 배열들이 없으면(구 스냅샷) 재도출로 폴백한다.
    const pipelineArraysPresent =
      pipeline !== undefined &&
      Array.isArray(pipeline.evolvepro_selected_variants) &&
      Array.isArray(pipeline.evolvepro_ranked_candidates) &&
      typeof pipeline.y_pred_map === "object" &&
      pipeline.y_pred_map !== null;
    // pipelineParamsAppliedToPatch: 위 REDESIGN_SENSITIVE_PARAM_KEYS 주석 참조.
    const canAttemptCsvSkip =
      savedEvolveproCsvFingerprint !== null &&
      pipelineArraysPresent &&
      pipelineParamsAppliedToPatch(patch);

    if (!alive()) return done(false);
    const currentCsvFingerprint = canAttemptCsvSkip
      ? await fingerprintSource(activeSourcePath)
      : null;
    if (!alive()) return done(false);
    const csvFingerprintMatches =
      canAttemptCsvSkip && fingerprintsEqual(savedEvolveproCsvFingerprint, currentCsvFingerprint);

    if (csvFingerprintMatches && pipeline) {
      // 지문 일치: loadEvolveproCsv 재도출을 건너뛰고 pipeline 블록을 그대로
      // 정본으로 쓴다. 비교 대상(재도출된 mutationText)이 없으므로 divergence
      // 판정도 하지 않는다(discardResultsIfVariantsDiverged 헤더 참조).
      // results 블록(designResults/poolVariants 등)은 이미 위 (c) 지점의
      // useAppStore.setState(patch)로 반영된 상태다. 여기서 만드는
      // pipelinePatch는 그 위에 pipeline 파생 상태(yPredMap 등)만 보충하는
      // 별도 setState이며, poolVariants를 다시 건드리지 않는다(이중 처리 아님).
      const pipelinePatch: Partial<AppState> = {
        evolveproCsvPath: activeSourcePath,
        yPredMap: pipeline.y_pred_map as AppState["yPredMap"],
        evolveproSelectedVariants: pipeline.evolvepro_selected_variants as AppState["evolveproSelectedVariants"],
        evolveproRankedCandidates: pipeline.evolvepro_ranked_candidates as AppState["evolveproRankedCandidates"],
        evolveproUsedVariantColumn:
          typeof pipeline.evolvepro_used_variant_column === "string"
            ? pipeline.evolvepro_used_variant_column
            : null,
        evolveproUsedScoreColumn:
          typeof pipeline.evolvepro_used_score_column === "string"
            ? pipeline.evolvepro_used_score_column
            : null,
        evolveproTotalCount:
          typeof pipeline.evolvepro_total_count === "number" ? pipeline.evolvepro_total_count : 0,
        evolveproFilteredCount:
          typeof pipeline.evolvepro_filtered_count === "number" ? pipeline.evolvepro_filtered_count : null,
        evolveproParetoExchanges:
          typeof pipeline.evolvepro_pareto_exchanges === "number" ? pipeline.evolvepro_pareto_exchanges : null,
        evolveproStepStats: (pipeline.evolvepro_step_stats ?? null) as AppState["evolveproStepStats"],
        domainStats: (
          typeof pipeline.domain_stats === "object" && pipeline.domain_stats !== null
            ? pipeline.domain_stats
            : {}
        ) as AppState["domainStats"],
      };
      if (!alive()) return done(false);
      useAppStore.setState(pipelinePatch);
      // loadEvolveproCsv가 하던 MAME 공유 store dual-write를 대신 수행한다.
      try {
        useMameAppStore.getState().setSharedEvolveproCsvPath(activeSourcePath);
      } catch {
        // Defensive: never let the cross-store hand-off break restore.
      }
    } else {
      try {
        // (d) loadEvolveproCsv도 store 쓰기(mutationText 갱신)라 호출 전에 막는다.
        if (!alive()) return done(false);
        await useAppStore.getState().loadEvolveproCsv(activeSourcePath);
        // (e) discardResultsIfVariantsDiverged는 setState로 결과물 블록을 비운다.
        //     await 뒤 취소됐다면 다음 프로젝트의 결과물을 지우게 되므로 막는다.
        if (!alive()) return done(false);
        // 재선택이 성공한 경우에만 비교한다. 로드가 실패하면 mutationText가
        // 갱신되지 않아 비교 자체가 무의미하다.
        resultsDiscarded = discardResultsIfVariantsDiverged(input?.mutation_text);
      } catch {
        // 조용히 넘기면 designResults는 복원되고 그 근거 variant 목록만 빠진
        // 어긋난 상태가 정상처럼 보인다. 호출부가 알리도록 기록한다.
        console.warn("[autosave] kuro: EVOLVEpro source load failed, continuing restore");
        unavailableInputs.push(activeSourcePath);
      }
    }
  }

  // 화면 위치(schema 5+). 저장된 위치가 있으면 그걸 쓰고, 없으면(구 스냅샷)
  // 기존 결과물 유무 휴리스틱으로 폴백한다. 결과물이 폐기됐으면 어느 쪽도
  // 적용하지 않는다(비어 있는 output.summary로 보내지 않는다).
  if (!alive()) return done(false);
  const navigation = snapshot.navigation as Record<string, unknown> | undefined;
  const hasSavedNavigation =
    navigation !== undefined &&
    isMajorStepId(navigation.current_major) &&
    isSubStepId(navigation.current_sub_step);
  if (!resultsDiscarded && hasSavedNavigation && navigation) {
    useAppStore.setState({
      currentMajor: navigation.current_major as MajorStepId,
      currentSubStep: navigation.current_sub_step as SubStepId,
      stepStatus: mergeStepStatus(navigation.step_status),
    });
  } else if (!resultsDiscarded && useAppStore.getState().designResults.length > 0) {
    // (f) setSubStep도 store 쓰기다. 취소 후 화면 위치를 옮기지 않는다.
    useAppStore.getState().setSubStep("output.summary");
  }

  // KURO 스냅샷은 Round 엔티티(rounds/active_round_id)를 복원하지 않는다.
  // MAME 스냅샷이 이미 이 상태를 단독 소유·복원한다(1290행 부근
  // applyMameSnapshot 참조). 여기서 또 setState하면 두 스냅샷 중 나중에
  // 착지한 쪽이 조용히 이겨 어느 쪽이 정본인지 알 수 없게 된다.

  return done(resultsDiscarded);
}

/**
 * 복원한 expected 워크북이 자기 자신과 어긋나면 알린다.
 *
 * `expected_mutations` 는 MAME 에게 well 좌표계다. 같은 파일의 프라이머 플레이트
 * 시트와 순서가 다르면 전 well 이 다른 설계로 채점되는데, 개수도 판정도 정상으로
 * 보여서 사용자가 알아챌 방법이 없다. 그래서 로딩 시점에 말해 준다.
 *
 * 검사 자체가 실패하는 것(구버전 사이드카, 읽을 수 없는 파일)은 복원을 막을 이유가
 * 아니므로 조용히 넘어간다. 없는 문제를 만들지도, 있는 문제를 감추지도 않는다.
 *
 * 문구는 분석 입력 패널의 PlateOrderNotice 와 같은 `buildPlateOrderMessage` 에서
 * 나온다. 같은 사실을 두 경로가 다른 말로 하면 사용자는 서로 다른 문제 둘로 읽는다.
 *
 * 2026-08-05 부터 알리는 데서 그치지 않고 `plateOrderFinding` 을 스토어에 써서
 * `selectCanRun` 이 실행을 막는다. 복원 직후는 경로가 모두 채워져 Run 이 바로
 * 눌리는 시점이라, 알림만 띄우면 워크북이 서로 다른 두 플레이트를 적고 있는 채로
 * 한 번의 클릭에 실행됐다. 등급은 blocking 하나뿐이다. 어느 시트가 실제로 분주한
 * 튜브인지는 이 화면의 어떤 입력에도 적혀 있지 않으므로 낮출 근거가 없다.
 */
async function reportPlateOrderMismatch(
  expectedPath: string,
  onMessage: (message: HydrationStatusMessage) => void,
  isCurrent: () => boolean,
): Promise<void> {
  if (!expectedPath) return;
  let report: PlateOrderReport | null = null;
  try {
    const raw = await sendMameRequest("check_plate_order", { path: expectedPath });
    // 구버전 사이드카는 이 메서드를 모르고, 테스트 대역은 undefined 를 준다. 응답
    // 모양을 확인하기 전에 필드를 읽으면 복원 자체가 깨지므로 여기서 걸러낸다.
    if (raw && typeof raw === "object" && "comparable" in raw) {
      report = raw as PlateOrderReport;
    }
  } catch {
    return;
  }
  if (!report || !isCurrent()) return;
  if (!isPlateOrderReportable(report)) return;

  const finding = { ...report, severity: "blocking" as const };
  // 말하는 것과 막는 것을 한자리에서 한다. 스토어에 쓰지 않으면 복원된 세션만
  // 게이트가 빠져, 같은 워크북이 새로 고른 경우에는 막히고 이어받은 경우에는
  // 실행되는 상태가 된다.
  useMameAppStore.setState({ plateOrderFinding: finding });
  onMessage({
    kind: "mame",
    variant: "plate_order_mismatch",
    message: buildPlateOrderMessage(finding, expectedPath).text,
  });
}

function basename(filePath: string): string {
  return filePath.split(/[/\\]/).pop() ?? filePath;
}

/**
 * 읽기 실패를 사용자에게 보여줄 문구.
 *
 * 읽기 실패 시점부터 해당 kind의 자동 저장 쓰기가 봉인되므로, 문구가 "중단됐다"는
 * 사실까지 전달해야 한다. 원인 추적을 위해 파일명과 원본 에러 메시지를 넘긴다.
 */
function readFailedMessage(filePath: string, error: Error): string {
  return i18next.t("autosaveHydration.readFailed", {
    filename: basename(filePath),
    cause: error.message,
  });
}

/**
 * 쓰기 실패 문구. scratch 승격(promoteScratchToProject)처럼 읽기가 아니라 쓰기가
 * 실패한 경로 전용이다. readFailedMessage를 재사용하면 "읽지 못했다"는 잘못된
 * 서술이 된다.
 */
function writeFailedMessage(filePath: string, error: Error): string {
  return i18next.t("autosaveHydration.writeFailed", {
    filename: basename(filePath),
    cause: error.message,
  });
}

/**
 * schema_too_new 봉인 사유. blockAutosaveWrites는 Error를 요구하는데 이 경로에는
 * 원본 예외가 없으므로 진단용 Error를 합성한다.
 */
function schemaTooNewReason(foundSchema: number, currentSchema: number): Error {
  return new Error(`autosave schema ${foundSchema} > supported ${currentSchema}`);
}

/**
 * scratch 자동 저장 읽기 결과를 KURO store에 반영하고 상태 메시지를 보낸다.
 * 프로젝트 스냅샷 처리와 동일한 variant 규칙(missing은 침묵)을 따른다.
 *
 * `source`는 문구만 가른다. "scratch"는 프로젝트 없이 이어서 작업하는 정상
 * 복원이고, "promotion"은 저장 안 된 세션 내용을 새 프로젝트로 물려받는
 * 경우라서 사용자가 구분할 수 있어야 한다.
 *
 * @returns 스냅샷이 실제로 store에 반영됐으면 true.
 */
async function applyScratchKuroSnapshot(
  result: ReadAutosaveResult,
  onMessage: (msg: HydrationStatusMessage) => void,
  isCurrent: () => boolean,
  source: "scratch" | "promotion" = "scratch",
): Promise<boolean> {
  if (result.status === "ok") {
    let outcome: KuroSnapshotApplyOutcome;
    try {
      outcome = await applyKuroSnapshot(result.snapshot, isCurrent);
    } catch (err) {
      console.warn("[autosave] kuro scratch: apply snapshot failed", err);
      onMessage({
        kind: "kuro",
        variant: "corrupted",
        message: i18next.t("autosaveHydration.corrupted", {
          filename: "kuro-scratch-autosave.json",
        }),
      });
      return false;
    }
    // 이미 다른 프로젝트로 넘어간 복원이면 false. 승격 쓰기·scratch 삭제 같은
    // 후속 부작용이 지나간 대상에 적용되면 안 된다.
    if (!isCurrent()) return false;
    const relative = formatRelativeTime(result.snapshot.saved_at);
    const message =
      source === "promotion"
        ? i18next.t("autosaveHydration.carriedFromScratch", { relative })
        : i18next.t("autosaveHydration.restored", { relative });
    onMessage({
      kind: "kuro",
      variant: "restored",
      message,
      savedAt: result.snapshot.saved_at,
    });
    if (outcome.unavailableInputs.length > 0) {
      onMessage({
        kind: "kuro",
        variant: "inputs_unavailable",
        message: i18next.t("autosaveHydration.inputsUnavailable", {
          count: outcome.unavailableInputs.length,
          paths: outcome.unavailableInputs.join(", "),
        }),
      });
    }
    if (outcome.resultsDiscarded) {
      onMessage({
        kind: "kuro",
        variant: "results_discarded",
        message: i18next.t("autosaveHydration.resultsDiscarded"),
      });
    }
    return true;
  }
  if (result.status === "read_failed") {
    // 읽지 못한 스냅샷 위에 빈 상태를 덮어쓰지 않도록 쓰기를 봉인한다.
    blockAutosaveWrites("kuro", result.error);
    onMessage({
      kind: "kuro",
      variant: "io_failed",
      message: readFailedMessage(result.filePath, result.error),
    });
    return false;
  }
  if (result.status === "corrupted") {
    onMessage({
      kind: "kuro",
      variant: "corrupted",
      message: i18next.t("autosaveHydration.corrupted", {
        filename: result.backupPath.split("/").pop() ?? "kuro-scratch-autosave.json",
      }),
    });
    return false;
  }
  if (result.status === "schema_too_new") {
    // 복원은 못 해도 쓰기는 계속 돌기 때문에, 봉인하지 않으면 미래 버전이 만든
    // 파일을 구 schema가 덮어써 일방향 손실이 난다. read_failed와 동일 처리.
    blockAutosaveWrites("kuro", schemaTooNewReason(result.foundSchema, KURO_SCHEMA));
    onMessage({
      kind: "kuro",
      variant: "schema_too_new",
      message: i18next.t("autosaveHydration.schemaTooNew"),
    });
  }
  // missing → 침묵
  return false;
}

/**
 * scratch 스냅샷을 프로젝트 자동 저장 파일로 확정하고 원본을 제거한다.
 *
 * 순서가 핵심이다. 프로젝트 파일 쓰기가 성공한 뒤에만 scratch 파일을 지운다.
 * 반대로 하면 쓰기 실패 시 양쪽 모두 사라진다. 삭제하지 않으면 이후 만드는
 * 모든 신규 프로젝트가 같은 scratch 내용을 다시 물려받는다.
 *
 * hydration 게이트가 살아 있는 구간이라 scheduleAutosave는 무시되므로
 * atomicWriteJson으로 직접 쓴다.
 *
 * `isCurrent`는 fs 왕복 사이의 취소 창을 막는다. 호출부에서 한 번만 검사하는
 * 방식으로는 부족하다. 호출 직전 검사와 이 함수 진입 사이에는 await가 없어
 * 아무것도 새로 잡아내지 못하고, 실제 위험 구간은 ensureAutosaveDir부터
 * deleteScratchAutosave까지의 왕복 사이이기 때문이다. 그 사이에 취소가 들어오면
 * 사용자가 버린 프로젝트로 작업이 옮겨지고 scratch 원본이 사라진다. 인자를
 * 생략하면 항상 진행한다(단위 테스트 경로).
 */
async function promoteScratchToProject(
  projectPath: string,
  isCurrent?: () => boolean,
): Promise<void> {
  const alive = () => isCurrent?.() ?? true;
  // 이관 시작 직전 최종 확인.
  if (!alive()) return;
  await ensureAutosaveDir(projectPath);
  if (!alive()) return;
  await atomicWriteJson(
    autosavePath(projectPath, "kuro"),
    // scratch에서 승격되는 경로다. scratch 스냅샷은 절대 경로만 담고 있으므로
    // 여기서 새 프로젝트 폴더 기준으로 상대화되어 이식 가능해진다.
    buildKuroSnapshot(useAppStore.getState(), projectPath),
  );
  // 순서는 이미 옳다(프로젝트 쓰기 성공 → scratch 삭제). 여기서 취소로 빠지면
  // scratch가 그대로 남는 쪽으로 기운다. 되돌릴 수 없는 삭제보다 중복이 낫다.
  if (!alive()) return;
  await deleteScratchAutosave();
}

// ─── Mame 죽은 경로 정리 ────────────────────────────────────────────────

/**
 * 복원된 MAME 입력 경로 중 존재하지 않는 것을 store 에서 비운다.
 *
 * 자동 저장은 사용자가 고른 절대 경로를 그대로 담으므로, 프로젝트 폴더를 옮기거나
 * 다른 PC 에서 열면 그 경로가 죽는다. 죽은 값을 남겨 두면 바로 뒤 자동 감지가
 * "이미 채워짐"으로 보고 건너뛰어(applyMameAutoDetect 의 `!store.xxx` 가드) 같은
 * 파일이 프로젝트 폴더 안에 있어도 다시 찾지 못한다.
 *
 * 비우기만 하고 다시 찾지는 않는다. 재탐색은 뒤이어 도는 자동 감지의 일이다.
 *
 * @returns 비운 필드의 사용자 표기 라벨. 자동 감지가 다시 채우지 못한 항목을
 *          호출부가 가려내 사용자에게 재지정을 요청하는 데 쓴다.
 */
async function clearStaleMamePaths(): Promise<MamePathField[]> {
  const store = useMameAppStore.getState();
  const stale = await findStaleMamePaths(
    {
      inputDir: store.inputDir,
      expectedPath: store.expectedPath,
      referencePath: store.referencePath,
      sampleMapPath: store.sampleMapPath,
      customBarcodesPath: store.rawRunParams.customBarcodesPath ?? "",
      sequencingSummaryPath: store.rawRunParams.sequencingSummaryPath ?? "",
    },
    exists,
  );
  if (stale.length === 0) return [];

  const fresh = useMameAppStore.getState();
  for (const field of stale) {
    switch (field) {
      case "inputDir":
        fresh.setInputDir("");
        break;
      case "expectedPath":
        fresh.setExpectedPath("");
        break;
      case "referencePath":
        fresh.setReferencePath("");
        break;
      case "sampleMapPath":
        fresh.setSampleMapPath("");
        break;
      case "customBarcodesPath":
        fresh.setParams({ rawRunParams: { customBarcodesPath: "" } });
        break;
      case "sequencingSummaryPath":
        fresh.setParams({ rawRunParams: { sequencingSummaryPath: "" } });
        break;
    }
  }
  return stale;
}

/** 스냅샷 input 블록에서 필드에 대응하는 저장값을 꺼낸다. */
const MAME_SNAPSHOT_KEY: Partial<Record<MamePathField, string>> = {
  inputDir: "input_dir",
  expectedPath: "expected_path",
  referencePath: "reference_path",
  sampleMapPath: "sample_map_path",
};

/**
 * 되찾지 못한 필드를 배너에 보여줄 형태로 바꾼다.
 *
 * 스냅샷 형식은 `lib/projectPath.ts` 규약이라 프로젝트 밖 값은 절대 경로
 * 그대로다. 거기서 이름을 얻어 "무엇을 다시 골라야 하는지" 를 보여준다.
 * 크기는 스냅샷에 없으므로 붙이지 않는다(대조는 이름으로 내려간다).
 * 저장값이 없으면 필드 라벨만 남긴다.
 */
function describeMissingInput(
  field: MamePathField,
  input: Record<string, unknown> | undefined,
): MissingInput {
  const key = MAME_SNAPSHOT_KEY[field];
  const stored = key ? input?.[key] : undefined;
  return typeof stored === "string" && isExternalPath(stored)
    ? { field, name: inputBasename(stored) }
    : { field, name: i18next.t(MAME_PATH_LABEL_KEYS[field]) };
}

/** 자동 감지가 끝난 뒤에도 여전히 비어 있는 필드만 남긴다. */
function stillMissing(fields: MamePathField[]): MamePathField[] {
  const store = useMameAppStore.getState();
  const value: Record<MamePathField, string> = {
    inputDir: store.inputDir,
    expectedPath: store.expectedPath,
    referencePath: store.referencePath,
    sampleMapPath: store.sampleMapPath,
    customBarcodesPath: store.rawRunParams.customBarcodesPath ?? "",
    sequencingSummaryPath: store.rawRunParams.sequencingSummaryPath ?? "",
  };
  return fields.filter((f) => !value[f]);
}

// ─── Mame 자동 탐지 ──────────────────────────────────────────────────────

/**
 * MAME 입력 파일 자동 탐지를 실행하고 빈 필드를 채운다.
 *
 * - mame_context.json 우선 시도 (detectProjectFiles 내부에서 처리)
 * - 이미 채워진 store 필드는 보호
 * - onMessage 콜백: 채워진 필드 목록 또는 "no new files" 전달
 *
 * Re-detect 버튼이나 외부에서 직접 호출할 수 있도록 export.
 *
 * `isCurrent`를 주면 store를 쓰는 statement 직전마다 취소 여부를 재확인하고,
 * 취소됐으면 그 지점에서 즉시 빠진다. 특히 detectProjectFiles·detectFromInputDir의
 * await가 resolve된 뒤에야 useMameAppStore.getState()를 캡처하기 때문에, 그 사이
 * 다른 프로젝트의 resetMameAll이 돌면 이전 프로젝트의 탐지 결과가 새 프로젝트의
 * 빈 필드에 그대로 주입된다. 인자를 생략하면 항상 진행한다(Re-detect 버튼 경로).
 */
export async function applyMameAutoDetect(
  projectPath: string,
  onMessage: (filled: string[]) => void,
  isCurrent?: () => boolean,
): Promise<void> {
  const alive = () => isCurrent?.() ?? true;
  const detected = await detectProjectFiles(projectPath);
  // await 동안 취소됐으면 store 캡처 자체를 하지 않는다. 여기서 끊지 않으면
  // 아래 빈 필드 판정이 다음 프로젝트의 store를 읽고 쓰게 된다.
  if (!alive()) return;
  const store = useMameAppStore.getState();
  const filled: string[] = [];

  // store.inputDir가 비어있었는지 기록 (setInputDir 이전 캡처)
  const inputDirWasEmpty = !store.inputDir;

  // 아래 가드는 setter 하나마다 반복한다. 지금은 사이에 await가 없어 한 번만
  // 검사해도 같은 결과지만, 나중에 setter 사이에 await가 끼어도 취소 창이 생기지
  // 않게 쓰기 statement 단위로 유지한다.
  if (inputDirWasEmpty && detected.inputDir) {
    if (!alive()) return;
    store.setInputDir(detected.inputDir);
    filled.push(i18next.t("autosaveHydration.fieldRunFolder"));
  }
  if (!store.referencePath && detected.referencePath) {
    if (!alive()) return;
    store.setReferencePath(detected.referencePath);
    filled.push(i18next.t("autosaveHydration.fieldReference"));
  }
  if (!store.expectedPath && detected.expectedPath) {
    if (!alive()) return;
    store.setExpectedPath(detected.expectedPath);
    filled.push(i18next.t("autosaveHydration.fieldExpected"));
  }
  if (!store.sampleMapPath && detected.sampleMapPath) {
    if (!alive()) return;
    store.setSampleMapPath(detected.sampleMapPath);
    filled.push(i18next.t("autosaveHydration.fieldSampleMap"));
  }
  if (!store.rawRunParams.customBarcodesPath && detected.customBarcodesPath) {
    if (!alive()) return;
    store.setParams({ rawRunParams: { customBarcodesPath: detected.customBarcodesPath } });
    filled.push(i18next.t("autosaveHydration.fieldCustomBarcodes"));
  }
  if (!store.rawRunParams.sequencingSummaryPath && detected.sequencingSummaryPath) {
    if (!alive()) return;
    store.setParams({ rawRunParams: { sequencingSummaryPath: detected.sequencingSummaryPath } });
    filled.push(i18next.t("autosaveHydration.fieldSequencingSummary"));
  }

  // inputDir가 비어있었고 새로 설정되었으며, inputDir ≠ projectPath 인 경우
  //, MinKNOW run 폴더 내부를 추가 스캔해 남은 빈 필드를 보충한다.
  if (inputDirWasEmpty && detected.inputDir && detected.inputDir !== projectPath) {
    const fromInputDir = await detectFromInputDir(detected.inputDir);
    // 두 번째 await 뒤 재확인. storeAfter 캡처가 다음 프로젝트 상태를 잡는 것을 막는다.
    if (!alive()) return;
    const storeAfter = useMameAppStore.getState();

    if (!storeAfter.referencePath && fromInputDir.referencePath) {
      if (!alive()) return;
      storeAfter.setReferencePath(fromInputDir.referencePath);
      filled.push(i18next.t("autosaveHydration.fieldReference"));
    }
    if (!storeAfter.expectedPath && fromInputDir.expectedPath) {
      if (!alive()) return;
      storeAfter.setExpectedPath(fromInputDir.expectedPath);
      filled.push(i18next.t("autosaveHydration.fieldExpected"));
    }
    if (!storeAfter.sampleMapPath && fromInputDir.sampleMapPath) {
      if (!alive()) return;
      storeAfter.setSampleMapPath(fromInputDir.sampleMapPath);
      filled.push(i18next.t("autosaveHydration.fieldSampleMap"));
    }
    if (!storeAfter.rawRunParams.customBarcodesPath && fromInputDir.customBarcodesPath) {
      if (!alive()) return;
      storeAfter.setParams({ rawRunParams: { customBarcodesPath: fromInputDir.customBarcodesPath } });
      filled.push(i18next.t("autosaveHydration.fieldCustomBarcodes"));
    }
    if (!storeAfter.rawRunParams.sequencingSummaryPath && fromInputDir.sequencingSummaryPath) {
      if (!alive()) return;
      storeAfter.setParams({ rawRunParams: { sequencingSummaryPath: fromInputDir.sequencingSummaryPath } });
      filled.push(i18next.t("autosaveHydration.fieldSequencingSummary"));
    }
  }

  const storeAfterDetection = useMameAppStore.getState();
  if (!storeAfterDetection.expectedPath) {
    try {
      const sdmPrimer = await getLatestArtifact("sdm_primer_xlsx");
      if (sdmPrimer?.path && !useMameAppStore.getState().expectedPath) {
        useMameAppStore.getState().setExpectedPath(sdmPrimer.path);
        filled.push(i18next.t("autosaveHydration.fieldExpected"));
      }
    } catch (err) {
      console.warn("[autosave] mame: SDM primer artifact lookup failed", err);
    }
  }

  onMessage(filled);
}

// ─── Mame 복원 ────────────────────────────────────────────────────────────

/**
 * @param projectPath schema 4+ 스냅샷의 `project://` 경로를 되돌릴 기준 폴더.
 *   구 스냅샷의 절대 경로는 기준과 무관하게 그대로 통과한다.
 */
/**
 * raw_run_params 안의 경로 두 개를 현재 환경의 절대 경로로 되돌린다.
 *
 * schema 4 부터 이 둘도 `project://` 로 저장된다. 구 스냅샷은 절대 경로이고
 * `fromPortablePath` 가 접두사 없는 값을 그대로 통과시키므로 그대로 읽힌다.
 * params 자체가 없으면 undefined 를 넘겨 store 기본값을 쓰게 한다.
 */
function resolveRawRunParams(
  raw: unknown,
  projectPath: string | null | undefined,
): RawRunParams | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const params = raw as RawRunParams;
  const base = projectPath ?? null;
  return {
    ...params,
    customBarcodesPath: fromPortablePath(base, params.customBarcodesPath ?? ""),
    sequencingSummaryPath: fromPortablePath(base, params.sequencingSummaryPath ?? ""),
  };
}

function applyMameSnapshot(
  snapshot: MameAutosaveSnapshot,
  projectPath: string | null = null,
): void {
  const store = useMameAppStore.getState();
  const { input, parameters } = snapshot;

  store.setParams({
    mode: parameters.mode as Parameters<typeof store.setParams>[0]["mode"],
    ingestMode: parameters.ingest_mode as Parameters<typeof store.setParams>[0]["ingestMode"],
    inputMode: (parameters.input_mode as Parameters<typeof store.setParams>[0]["inputMode"]) ?? "raw_run",
    rawRunParams: resolveRawRunParams(parameters.raw_run_params, projectPath),
    cdsStart: parameters.cds_start,
    cdsEnd: parameters.cds_end,
    minFileSizeKb: parameters.min_file_size_kb,
    manyCutoff: parameters.many_cutoff,
  });
  // 프로젝트 폴더 안을 가리키던 입력은 여기서 현재 폴더 기준으로 되살아난다.
  // 폴더 밖 절대 경로는 그대로 복원되며, 옮긴 PC에 없으면 이어지는 자동 탐지가
  // 빈 필드를 프로젝트 디렉토리에서 채운다.
  const resolveMame = (value: string): string => fromPortablePath(projectPath, value);
  store.setInputDir(resolveMame(input.input_dir));
  store.setExpectedPath(resolveMame(input.expected_path));
  store.setReferencePath(resolveMame(input.reference_path));
  store.setOutputPath(resolveMame(input.output_path));
  const sampleMapPath = resolveMame(input.sample_map_path);
  if (sampleMapPath) store.setSampleMapPath(sampleMapPath);

  if (Array.isArray(snapshot.rounds)) {
    useRoundStore.setState({
      rounds: snapshot.rounds,
      active_round_id: snapshot.active_round_id ?? null,
    });
  }

  useMameAppStore.setState({
    validationErrors: [],
    analyzeMessage: i18next.t("autosaveHydration.workspaceRestored"),
  });

  const results = snapshot.results as Record<string, unknown> | undefined;
  if (results === undefined) return;

  const patch: Partial<MameAppState> = {};
  let hasReviewResults = false;
  if (Array.isArray(results.verdicts)) {
    patch.verdicts = results.verdicts as MameAppState["verdicts"];
    hasReviewResults = results.verdicts.length > 0;
  }
  if (Array.isArray(results.replicates)) {
    patch.replicates = results.replicates as MameAppState["replicates"];
  }
  if (typeof results.summary === "object") {
    patch.summary = results.summary as MameAppState["summary"];
    hasReviewResults = hasReviewResults || results.summary !== null;
  }
  if (typeof results.distribution_stats === "object") {
    patch.distributionStats = results.distribution_stats as MameAppState["distributionStats"];
  }
  if (Array.isArray(results.wells)) {
    patch.wells = results.wells as MameAppState["wells"];
  }
  if (typeof results.selected_well === "object") {
    patch.selectedWell = results.selected_well as MameAppState["selectedWell"];
  }
  if (typeof results.run_health === "object") {
    patch.runHealth = results.run_health as MameAppState["runHealth"];
  }
  if (typeof results.build_evolvepro_completion === "object") {
    patch.buildEvolveproCompletion = results.build_evolvepro_completion as MameAppState["buildEvolveproCompletion"];
  }
  if (typeof results.demux_result === "object") {
    patch.demuxResult = results.demux_result as MameAppState["demuxResult"];
  }
  if (typeof results.amplicon_length_estimate === "object") {
    patch.ampliconLengthEstimate = results.amplicon_length_estimate as MameAppState["ampliconLengthEstimate"];
  }
  if (typeof results.well_layout === "object") {
    patch.wellLayout = results.well_layout as MameAppState["wellLayout"];
  }
  if (hasReviewResults) {
    patch.mamePhase = "analyze";
    patch.currentMameSubStep = "analyze.review";
  }
  useMameAppStore.setState(patch);
}

// ─── Mame analyze-result 복원 ──────────────────────

/**
 * Restore a persisted analyze result (sibling result file) into BOTH the
 * sidecar and the store, then land on the 2.2 review view.
 *
 * Runs AFTER the input-snapshot restore. Independent of input-snapshot status:
 * the result file alone is sufficient to repopulate verdicts/replicates and the
 * plate view. Missing result file -> silent skip (returns false).
 *
 * Sequence (locked):
 *  1. load_analyze_result RPC (re-injects sidecar SidecarState; otherwise
 *     get_plate_data throws -32002 and Plate View breaks)
 *  2. store verdicts / replicates / summary / distribution_stats
 *  3. loadPlateData() (reads get_plate_data from the restored sidecar state)
 *  4. setMameSubStep("analyze.review")
 *
 * The persisted `result.replicates[].plate_verdicts` is replayed AS-IS; it is
 * the only lossless source for per-plate accent restoration.
 *
 * `isCurrent`를 주면 쓰기 statement 직전마다 취소 여부를 재확인한다. 여기서
 * load_analyze_result RPC는 사이드카 SidecarState를 갈아끼우는 쓰기라, 취소된
 * 복원이 완주하면 다음 프로젝트의 사이드카 상태와 Plate View가 이전 프로젝트
 * 결과로 덮인다. 인자를 생략하면 항상 진행한다(단위 테스트 경로).
 */
/**
 * 결과 파일 없이 자동 저장 스냅샷만으로 사이드카 분석 상태를 되살린다.
 *
 * 화면의 verdict 표는 `applyMameSnapshot` 이 스냅샷에서 직접 복원하는 반면,
 * 사이드카 `last_verdicts` 는 별도 결과 파일 경로(`restoreMameResult`)로만
 * 채워진다. 결과 파일이 없거나 읽히지 않으면 두 쪽이 어긋나 "표는 보이는데
 * 리포트·Excel 내보내기는 No prior analyze result 로 거부되는" 상태가 된다.
 * 스냅샷이 이미 verdicts·replicates·summary·distribution_stats 를 들고 있으므로
 * 같은 RPC 에 그대로 실어 보내면 그 간극이 사라진다.
 *
 * @returns 사이드카를 채웠으면 true. 스냅샷에 결과가 없으면 false.
 */
async function injectSnapshotResultsIntoSidecar(
  snapshot: MameAutosaveSnapshot,
  projectPath: string,
  isCurrent?: () => boolean,
): Promise<boolean> {
  const alive = () => isCurrent?.() ?? true;
  const results = snapshot.results;
  if (!results || !Array.isArray(results.verdicts) || results.verdicts.length === 0) {
    return false;
  }
  if (!alive()) return false;
  await sendMameRequest<LoadAnalyzeResultResponse>("load_analyze_result", {
    verdicts: results.verdicts,
    // output_path 는 사이드카가 후속 내보내기 기본 경로로만 쓴다. 스냅샷 값은
    // 프로젝트 상대 형태일 수 있으므로 현재 폴더 기준으로 되돌린다.
    replicates: results.replicates ?? [],
    output_path: fromPortablePath(projectPath, snapshot.input?.output_path ?? ""),
    summary: results.summary ?? null,
    distribution_stats: results.distribution_stats ?? null,
  });
  return alive();
}

async function restoreMameResult(
  projectPath: string,
  isCurrent?: () => boolean,
): Promise<boolean> {
  const alive = () => isCurrent?.() ?? true;
  const read = await readMameResultSnapshot(projectPath);
  if (read.status !== "ok") return false;
  // RPC 자체가 사이드카 쓰기다. 호출 전에 막아야 한다.
  if (!alive()) return false;

  const { result } = read.snapshot;
  const store = useMameAppStore.getState();

  await sendMameRequest<LoadAnalyzeResultResponse>("load_analyze_result", {
    verdicts: result.verdicts,
    replicates: result.replicates,
    output_path: result.output_path,
    summary: result.summary ?? null,
    distribution_stats: result.distribution_stats ?? null,
  });
  // RPC를 기다리는 동안 취소됐으면 store 반영은 하지 않는다.
  if (!alive()) return false;

  store.setVerdicts(result.verdicts);
  if (!alive()) return false;
  store.setReplicates(result.replicates);
  if (!alive()) return false;
  store.setSummary(result.summary);
  if (!alive()) return false;
  // Restored runs must be able to explain a zero-verdict outcome too, so carry
  // the demux yield out of the persisted response instead of dropping it.
  store.setAnalyzeYield(pickAnalyzeYield(result));
  if (!alive()) return false;
  store.setDistributionStats(result.distribution_stats ?? null);
  if (!alive()) return false;
  await store.loadPlateData();
  if (!alive()) return false;
  // A8: the run-health panel ("Plate별 verdict 분포") reads get_run_health from the
  // restored sidecar state; without this it stays null and shows "설정 미완료".
  await store.loadRunHealth();
  if (!alive()) return false;
  store.setMameSubStep("analyze.review");
  return true;
}

// ─── 훅 ──────────────────────────────────────────────────────────────────

/** 진행 중인 복원 1건. 취소 플래그와 자동 저장 게이트 래치를 함께 들고 다닌다. */
interface HydrationRun {
  cancelled: boolean;
  /** 이 run의 beginHydration에 대응하는 endHydration이 이미 나갔으면 true. */
  gateReleased: boolean;
}

/**
 * 이 run이 잡고 있던 자동 저장 게이트를 푼다.
 *
 * 해제 지점이 넷(cancel, 언마운트 cleanup, 프로젝트 전환, IIFE finally)이라 그냥
 * endHydration을 부르면 같은 run에 대해 최대 4번 감소한다. gateReleased는 run
 * 1개당 한 번만 넘어가는 일회성 래치라서, 먼저 도착한 호출 하나만 실제로 감소시킨다. 그래서
 * beginHydration 1회와 endHydration 1회가 항상 짝을 이루고 hydrationDepth가
 * 음수로 내려가지 않는다. (endHydration 자체도 0에서 멈추지만, 그건 실수를 덮는
 * 안전망일 뿐 짝 맞춤의 근거가 아니다.)
 */
function releaseHydrationGate(run: HydrationRun): void {
  if (run.gateReleased) return;
  run.gateReleased = true;
  endHydration();
}

/**
 * 프로젝트 진입 시 kuro + mame 자동 저장 파일을 복원한다.
 *
 * - path가 null이면 즉시 종료.
 * - scratch 포함 projectPath 변경마다 이전 프로젝트의 in-memory KURO/MAME 상태를 먼저 비운다.
 * - scratch 프로젝트는 앱 데이터 디렉토리의 KURO scratch 스냅샷만 복원한다.
 * - 프로젝트 KURO 스냅샷이 없으면 scratch 스냅샷으로 폴백한다.
 * - 같은 projectPath/scratch 조합이 연속 렌더되는 경우만 중복 복원을 막는다.
 */
export function useAutosaveHydration(
  onMessage: (msg: HydrationStatusMessage) => void,
): AutosaveHydrationHandle {
  const project = useKumaProject();
  /** 마지막으로 복원을 시작한 project key. 같은 경로/모드 연속 렌더만 중복 방지. */
  const lastHydratedKey = useRef<string | null>(null);
  const [hydrating, setHydrating] = useState(false);
  /**
   * 현재 복원 단계. 오버레이가 이 값만 보고 진행 문구를 고른다. 호출부의 범용
   * 상태바를 경유하지 않으므로 4초 자동 소멸이나 다른 메시지와의 경합이 없다.
   */
  const [phase, setPhase] = useState<HydrationPhase | null>(null);
  /**
   * 진행 중인 복원 1건. 취소 플래그를 effect 클로저 지역 변수가 아니라 이 객체에
   * 두어 cancel()이 닿게 한다.
   *
   * cleanup에서 취소하지 않는 이유: onMessage는 t에 의존하는 useCallback이라
   * 언어 변경만으로도 effect가 같은 key로 재실행되고, hydrating setState 자체도
   * 재렌더를 유발한다. cleanup이 취소하면 그 재실행이 dup-key로 조기 return하는
   * 사이 진행 중인 복원만 죽는다. 취소는 프로젝트 전환(새 run이 ref를 교체),
   * 언마운트(아래 전용 effect), cancel() 세 경로에서만 일어난다.
   */
  const activeRunRef = useRef<HydrationRun | null>(null);

  // 언마운트 cleanup. StrictMode의 모의 언마운트에서도 실행된다. 그래서 ref를
  // 전부 비워 뒤이은 재마운트가 복원을 처음부터 다시 시작하게 한다. cancelled만
  // 세우고 lastHydratedKey를 남기면 재마운트한 메인 effect가 dup-key 가드에 걸려
  // 조기 return하고, 살아남은 run은 첫 isCurrent()에서 죽는다. 그 조합은 dev
  // 빌드에서 resetAll만 돌고 자동 저장이 한 번도 복원되지 않는 상태를 만든다.
  useEffect(() => {
    return () => {
      const run = activeRunRef.current;
      if (run) {
        run.cancelled = true;
        // 언마운트로 죽는 run의 게이트도 즉시 푼다. 고아 IIFE의 finally를
        // 기다리면 그 사이 hydrationDepth가 남아 다음 프로젝트의 자동 저장이
        // 조용히 차단된다(cancel()과 같은 이유).
        releaseHydrationGate(run);
        activeRunRef.current = null;
      }
      // phase는 여기서 내리지 않는다. 언마운트 중 setState는 버려지고, 재마운트는
      // useState가 null로 새로 초기화한다. 살아남은 고아 run의 finally도
      // activeRunRef 비교에서 지므로 옛 phase를 되살리지 못한다.
      lastHydratedKey.current = null;
    };
  }, []);

  useEffect(() => {
    // 아래 두 조기 return 경로는 상태를 건드리지 않는다. setState를 넣으면
    // onMessage 신원이 매 렌더 바뀌는 호출부에서 렌더 루프가 된다.
    if (!project || !project.path) return;
    const { path, scratch } = project;
    const hydrationKey = `${scratch ? "scratch" : "project"}:${path}`;
    if (lastHydratedKey.current === hydrationKey) return;
    lastHydratedKey.current = hydrationKey;

    // 이전 복원이 남아 있으면 여기서 끊고 게이트도 즉시 푼다(프로젝트 전환 경로).
    // 이전 run의 finally를 기다리면 고아가 된 사이드카 RPC(MAME 기본 타임아웃
    // 60초)가 끝날 때까지 hydrationDepth가 남아, B의 복원이 끝나도 B의
    // scheduleAutosave가 조용히 차단되고 인디케이터는 계속 켜짐으로 남는다.
    // 안전한 이유는 둘이다. (1) gateReleased 래치가 run당 하나라 뒤늦게 도착하는
    // 이전 run의 finally는 두 번 감소시키지 않는다. (2) 이 해제와 아래
    // beginHydration 사이에는 await가 없다(지역 선언과 setHydrating(true)뿐).
    // 그래서 게이트가 0으로 스쳐 지나가는 창에 scheduleAutosave가 끼어들 수 없다.
    const previousRun = activeRunRef.current;
    if (previousRun) {
      previousRun.cancelled = true;
      releaseHydrationGate(previousRun);
    }
    const run: HydrationRun = { cancelled: false, gateReleased: false };
    activeRunRef.current = run;
    const isCurrent = () =>
      !run.cancelled && activeRunRef.current === run && lastHydratedKey.current === hydrationKey;
    /**
     * 이 run이 아직 최신일 때만 진행 단계를 갱신한다. await 뒤에 재개한 stale run이
     * 새 run의 phase를 덮어쓰는 것을 막는다.
     */
    const setRunPhase = (next: HydrationPhase) => {
      if (!isCurrent()) return;
      setPhase(next);
    };

    setHydrating(true);

    // 자동 저장 스케줄을 복원이 끝날 때까지 막는다. resetAll이 새 리터럴을 넣는
    // 순간 구독자(useKuroAutosave)가 스케줄을 걸고, 그 스냅샷은 복원 전 빈
    // 상태다. loadSequence/loadEvolveproCsv는 사이드카 RPC라 디바운스 1.5초를
    // 넘길 수 있어, 게이트가 없으면 빈 스냅샷이 먼저 디스크에 착지한다.
    // 동기 호출이어야 한다. 아래 IIFE의 첫 await 전에 resetAll이 실행된다.
    beginHydration();

    void (async () => {
      setRunPhase("reset");
      useAppStore.getState().resetAll({ preserveWorkspaceArtifacts: true });
      await resetMameAll({ preserveWorkspaceArtifacts: true });

      // scratch(프로젝트 없음): 앱 데이터 디렉토리 스냅샷만 KURO에 복원한다.
      // 워크스페이스 레지스트리·MAME 복원·자동 탐지는 프로젝트 전용이라 건너뛴다.
      if (scratch) {
        // scratch 스냅샷도 KURO 복원이라 같은 단계로 묶는다.
        setRunPhase("kuro");
        const scratchResult = await readScratchAutosave(KURO_SCHEMA);
        if (!isCurrent()) return;
        // 읽기에 성공한 경우에만 봉인을 해제한다. read_failed/schema_too_new는
        // 아래에서 다시 봉인하므로 여기서 풀면 안 된다.
        if (scratchResult.status !== "read_failed" && scratchResult.status !== "schema_too_new") {
          clearAutosaveBlock("kuro");
        }
        await applyScratchKuroSnapshot(scratchResult, onMessage, isCurrent);
        return;
      }

      setRunPhase("workspace");
      try {
        await openWorkspace(path);
      } catch (err) {
        console.warn("[autosave] workspace registry open failed", err);
      }
      if (!isCurrent()) return;

      // 두 스냅샷을 함께 읽지만 이어지는 긴 구간(applyKuroSnapshot의 사이드카
      // 왕복)이 KURO 몫이라 여기부터 "kuro"로 둔다.
      setRunPhase("kuro");
      const [kuroResult, mameResult] = await Promise.all([
        readAutosave(path, "kuro", KURO_SCHEMA),
        readAutosave(path, "mame", MAME_SCHEMA),
      ]);
      if (!isCurrent()) return;

      // 읽기에 성공한 kind만 봉인을 해제한다. read_failed/schema_too_new는
      // 아래에서 다시 건다.
      if (kuroResult.status !== "read_failed" && kuroResult.status !== "schema_too_new") {
        clearAutosaveBlock("kuro");
      }
      if (mameResult.status !== "read_failed" && mameResult.status !== "schema_too_new") {
        clearAutosaveBlock("mame");
      }

      // ── kuro 결과 처리
      if (kuroResult.status === "ok") {
        try {
          const outcome = await applyKuroSnapshot(kuroResult.snapshot, isCurrent, path);
          if (!isCurrent()) return;
          onMessage({
            kind: "kuro",
            variant: "restored",
            message: i18next.t("autosaveHydration.restored", { relative: formatRelativeTime(kuroResult.snapshot.saved_at) }),
            savedAt: kuroResult.snapshot.saved_at,
          });
          if (outcome.unavailableInputs.length > 0) {
            onMessage({
              kind: "kuro",
              variant: "inputs_unavailable",
              message: i18next.t("autosaveHydration.inputsUnavailable", {
                count: outcome.unavailableInputs.length,
                paths: outcome.unavailableInputs.join(", "),
              }),
            });
          }
          if (outcome.resultsDiscarded) {
            onMessage({
              kind: "kuro",
              variant: "results_discarded",
              message: i18next.t("autosaveHydration.resultsDiscarded"),
            });
          }
        } catch (err) {
          // scratch 경로(applyScratchKuroSnapshot)는 이미 corrupted를 알린다.
          // 프로젝트 경로만 침묵하면 같은 실패가 화면에 안 뜨므로 맞춘다.
          console.warn("[autosave] kuro: apply snapshot failed", err);
          onMessage({
            kind: "kuro",
            variant: "corrupted",
            message: i18next.t("autosaveHydration.corrupted", {
              filename: "kuro.json",
            }),
          });
        }
      } else if (kuroResult.status === "corrupted") {
        onMessage({
          kind: "kuro",
          variant: "corrupted",
          message: i18next.t("autosaveHydration.corrupted", { filename: kuroResult.backupPath.split("/").pop() ?? "kuro.json.bad-…" }),
        });
      } else if (kuroResult.status === "read_failed") {
        // 파일이 없는 것과 못 읽은 것은 다르다. 못 읽은 파일 위에 빈 상태를
        // 덮어쓰지 않도록 kuro 쓰기를 봉인하고 사용자에게 알린다.
        blockAutosaveWrites("kuro", kuroResult.error);
        onMessage({
          kind: "kuro",
          variant: "io_failed",
          message: readFailedMessage(kuroResult.filePath, kuroResult.error),
        });
      } else if (kuroResult.status === "schema_too_new") {
        // 복원만 건너뛰고 쓰기를 계속 두면 미래 버전 스냅샷을 구 schema가
        // 덮어써 일방향 손실이 난다. read_failed와 동일하게 봉인한다.
        blockAutosaveWrites("kuro", schemaTooNewReason(kuroResult.foundSchema, KURO_SCHEMA));
        onMessage({
          kind: "kuro",
          variant: "schema_too_new",
          message: i18next.t("autosaveHydration.schemaTooNew"),
        });
      } else if (kuroResult.status === "missing") {
        // 프로젝트 스냅샷이 없으면 scratch 스냅샷으로 이어서 작업하게 한다.
        const scratchResult = await readScratchAutosave(KURO_SCHEMA);
        if (!isCurrent()) return;
        if (scratchResult.status === "ok") {
          const applied = await applyScratchKuroSnapshot(
            scratchResult,
            onMessage,
            isCurrent,
            "promotion",
          );
          // 승격한 scratch 스냅샷은 여기서 소비된다. 지우지 않으면 이후 만드는
          // 신규 프로젝트마다 같은 FASTA·mutation·designResults가 다시 새어
          // 나가고, 다음 자동 저장이 그것을 프로젝트 파일에 영구화한다.
          if (applied) {
            try {
              await promoteScratchToProject(path, isCurrent);
            } catch (err) {
              const error = err instanceof Error ? err : new Error(String(err));
              console.warn("[autosave] kuro: scratch promotion failed", error);
              onMessage({
                kind: "kuro",
                variant: "io_failed",
                // 이 경로는 읽기가 아니라 프로젝트 파일 쓰기가 실패한 경우다.
                message: writeFailedMessage(autosavePath(path, "kuro"), error),
              });
            }
          }
        } else if (scratchResult.status === "read_failed") {
          // scratch 파일을 못 읽었으면 사실만 알린다. 이후 쓰기 대상은 이 파일이
          // 아니라 프로젝트 파일이므로 kuro 쓰기를 봉인하지는 않는다.
          onMessage({
            kind: "kuro",
            variant: "io_failed",
            message: readFailedMessage(scratchResult.filePath, scratchResult.error),
          });
        }
      }
      if (!isCurrent()) return;

      // ── mame 결과 처리
      if (mameResult.status === "ok") {
        try {
          applyMameSnapshot(mameResult.snapshot as MameAutosaveSnapshot, path);
          if (!isCurrent()) return;
          onMessage({
            kind: "mame",
            variant: "restored",
            message: i18next.t("autosaveHydration.restored", { relative: formatRelativeTime(mameResult.snapshot.saved_at) }),
            savedAt: mameResult.snapshot.saved_at,
          });
        } catch (err) {
          console.warn("[autosave] mame: apply snapshot failed", err);
        }
      } else if (mameResult.status === "read_failed") {
        // kuro와 같은 이유로 mame 쓰기도 봉인한다. mame 자동 저장 역시 store
        // 구독 기반이라, 못 읽은 mame.json 위에 초기화된 상태가 덮어써진다.
        blockAutosaveWrites("mame", mameResult.error);
        onMessage({
          kind: "mame",
          variant: "io_failed",
          message: readFailedMessage(mameResult.filePath, mameResult.error),
        });
      } else if (mameResult.status === "corrupted") {
        onMessage({
          kind: "mame",
          variant: "corrupted",
          message: i18next.t("autosaveHydration.corrupted", { filename: mameResult.backupPath.split("/").pop() ?? "mame.json.bad-…" }),
        });
      } else if (mameResult.status === "schema_too_new") {
        // kuro와 동일 이유로 봉인한다.
        blockAutosaveWrites("mame", schemaTooNewReason(mameResult.foundSchema, MAME_SCHEMA));
        onMessage({
          kind: "mame",
          variant: "schema_too_new",
          message: i18next.t("autosaveHydration.schemaTooNew"),
        });
      }
      if (!isCurrent()) return;
      // missing → 침묵

      // ── mame analyze-result 복원: 입력 스냅샷 복원 후, 결과 파일이 있으면
      //    사이드카 + store 재구성 후 2.2 review 뷰로 진입. RPC 실패가 입력
      //    스냅샷 "apply snapshot failed" 메시지를 오염시키지 않도록 별도 try/catch.
      setRunPhase("mame");
      try {
        const restored = await restoreMameResult(path, isCurrent);
        if (!isCurrent()) return;
        if (restored) {
          onMessage({
            kind: "mame",
            variant: "restored",
            message: i18next.t("autosaveHydration.workspaceRestored"),
          });
        } else if (mameResult.status === "ok") {
          // 결과 파일이 없거나 못 읽었다. 화면에는 스냅샷의 verdict 표가 이미
          // 복원돼 있으므로, 사이드카만 비워 두면 리포트·Excel 내보내기가
          // "No prior analyze result" 로 거부된다. 같은 값으로 채워 맞춘다.
          await injectSnapshotResultsIntoSidecar(
            mameResult.snapshot as MameAutosaveSnapshot,
            path,
            isCurrent,
          );
        }
      } catch (err) {
        console.warn("[autosave] mame: analyze-result restore failed", err);
      }
      if (!isCurrent()) return;

      // ── 죽은 경로 정리: 복원된 절대 경로 중 더 이상 존재하지 않는 것을 비운다.
      //    비우지 않으면 바로 아래 자동 감지가 "이미 채워짐"으로 보고 건너뛰어,
      //    같은 파일이 프로젝트 폴더 안에 있어도 영영 못 찾는다.
      const droppedFields = await clearStaleMamePaths();
      if (!isCurrent()) return;

      // ── auto-detect: autosave 복원 후 여전히 비어있는 필드를 프로젝트 디렉토리에서 채운다
      setRunPhase("detect");
      await applyMameAutoDetect(
        path,
        (filled) => {
          if (!isCurrent()) return;
          if (filled.length > 0) {
            onMessage({
              kind: "mame",
              variant: "restored",
              message: i18next.t("autosaveHydration.autoDetected", { fields: filled.join(", ") }),
            });
          }
        },
        isCurrent,
      );
      if (!isCurrent()) return;

      // 자동 감지가 되찾지 못한 항목만 남는다. raw MinKNOW run 폴더처럼 프로젝트
      // 밖에 있던 입력이 여기 걸린다. 조용히 비워 두면 사용자는 값이 사라진 줄도
      // 모르므로, 무엇을 다시 고르면 되는지 이름으로 알린다.
      const unresolved = stillMissing(droppedFields);
      // 이전 프로젝트의 잔여 항목이 남지 않도록 매 복원마다 통째로 교체한다.
      useMissingInputs.getState().setMissing(
        unresolved.map((field) =>
          describeMissingInput(
            field,
            mameResult.status === "ok"
              ? ((mameResult.snapshot as MameAutosaveSnapshot).input as unknown as Record<string, unknown>)
              : undefined,
          ),
        ),
      );
      // 복원한 expected 워크북이 자기 자신과 어긋나는지 본다. v0.14.3 이전 export 가
      // 그렇고, 조용히 넘기면 그 프로젝트의 모든 판정이 틀린 배치로 나온다.
      void reportPlateOrderMismatch(
        useMameAppStore.getState().expectedPath,
        onMessage,
        isCurrent,
      );
      if (unresolved.length > 0) {
        onMessage({
          kind: "mame",
          variant: "restored",
          message: i18next.t("autosaveHydration.pathsMoved", {
            fields: unresolved.map((f) => i18next.t(MAME_PATH_LABEL_KEYS[f])).join(", "),
          }),
        });
      }
    })().finally(() => {
      // 어느 경로로 끝나든(정상 종료, 조기 return, 예외) 게이트를 반드시 푼다.
      // 게이트가 남으면 이후 자동 저장이 통째로 죽는다. cancel()이나 언마운트가
      // 먼저 풀었으면 gateReleased 래치가 이중 감소를 막는다.
      releaseHydrationGate(run);
      // 취소 후 같은 프로젝트로 즉시 재진입하면 옛 IIFE의 finally가 새 복원의
      // 표시를 꺼버린다. 이 run이 아직 최신일 때만 끈다. 이 비교가 false면 취소·
      // 전환·언마운트 중 하나로 이미 소유권이 넘어간 뒤라 phase도 건드리지 않는다.
      if (activeRunRef.current === run) {
        setHydrating(false);
        setPhase(null);
      }
    });
  }, [project?.path, project?.scratch, onMessage]);

  const cancel = useCallback(() => {
    const run = activeRunRef.current;
    if (run) {
      run.cancelled = true;
      // 게이트를 즉시 푼다. IIFE의 finally는 고아가 된 사이드카 RPC(MAME 기본
      // 타임아웃 60초)가 끝나야 실행되고, hydrationDepth는 모듈 레벨 변수라
      // MainShell 언마운트에도 살아남는다. 그 사이 취소 후 진입한 다음 프로젝트의
      // scheduleAutosave가 조용히 차단된다(차단은 이벤트를 발행하지 않아 UI
      // 인디케이터는 계속 켜짐으로 남는다).
      releaseHydrationGate(run);
      activeRunRef.current = null;
    }
    // lastHydratedKey는 건드리지 않는다. 여기서 비우면 훅이 마운트된 채 취소된 뒤
    // 언어를 바꿀 때(onMessage가 t 의존 useCallback이라 신원이 바뀐다) effect가
    // 같은 프로젝트 키로 재실행되어 resetAll이 다시 돌고 사용자 작업이 날아간다.
    // 정상 재진입(App.tsx의 kuma:return-to-home → MainShell 언마운트 → 재진입)은
    // 언마운트 effect가 이미 키를 비우므로 새 ref로 정상 복원되고, 마운트를 유지한
    // 채 같은 키로 effect가 재실행되는 경우는 dup-key 가드에 걸려 skip되어야 옳다.
    setHydrating(false);
    // 위에서 activeRunRef를 비웠으므로 이 시점에 진행 중인 run은 없다. 뒤늦게
    // 도착하는 고아 run의 finally도 activeRunRef 비교에서 져 phase를 되살리지 못한다.
    setPhase(null);
  }, []);

  return { hydrating, phase, cancel };
}
