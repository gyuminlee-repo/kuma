/**
 * reRun.ts — §12 Reproducibility: manifest 기반 재현 실행
 *
 * `tryHandleManifestDrop`  : DnD 핸들러에서 호출. manifest 경로 감지 후
 *                             로드 + 검증 + 모달 트리거 콜백 실행.
 * `reRunFromManifest`      : 확인 모달에서 "Re-run" 클릭 시 호출.
 *                             method 별 store action 을 실행한다.
 *
 * 지원 method:
 *   design_sdm_primers      → kuro: loadSequence + setMutationText + designPrimers
 *   merge_for_evolvepro     → mame: mergeForEvolvepro
 *
 * 미지원 method (export_order / export_mapping / export_excel):
 *   모달에서 안내 메시지만 표시. 실제 re-run 실행 안 함.
 */

import { readFile } from "@tauri-apps/plugin-fs";
import i18next from "i18next";
import { loadManifestFromFile, type RunManifest } from "./runManifest";
import { useAppStore } from "@/store/appStore";
import { useActivityStore } from "@/store/mame/activitySlice";

// ── 지원 method 목록 ──────────────────────────────────────────────────────────

const RUNNABLE_METHODS = new Set(["design_sdm_primers", "merge_for_evolvepro"]);

const EXPORT_ONLY_METHODS = new Set([
  "export_order",
  "export_mapping",
  "export_excel",
]);

// ── manifest 파일 확장자 ───────────────────────────────────────────────────────

const MANIFEST_SUFFIXES = [".run.json"];

function isManifestPath(filePath: string): boolean {
  const lower = filePath.toLowerCase();
  // "run.json" 단독 파일명 혹은 "*.run.json" 패턴 모두 허용
  if (lower === "run.json" || lower.endsWith("/run.json")) return true;
  return MANIFEST_SUFFIXES.some((s) => lower.endsWith(s));
}

// ── SHA-256 검증 ──────────────────────────────────────────────────────────────

/**
 * 파일 바이트를 읽어 SHA-256 hex digest 를 계산한다.
 * Uint8Array → ArrayBuffer → crypto.subtle.digest 순서로 처리.
 */
async function sha256Hex(filePath: string): Promise<string> {
  const bytes = await readFile(filePath);
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ── 입력 파일 검증 결과 ───────────────────────────────────────────────────────

export interface InputVerifyResult {
  /** 경고가 있는 입력 파일 키 목록 */
  mismatched: string[];
  /** 경로 자체가 없는 입력 파일 키 목록 */
  missing: string[];
}

/**
 * manifest.inputs 의 각 파일 경로 존재 여부와 SHA-256 일치를 검증한다.
 * 실패 시 silent fallback 없이 mismatched/missing 목록으로 반환한다.
 */
export async function verifyInputs(manifest: RunManifest): Promise<InputVerifyResult> {
  const mismatched: string[] = [];
  const missing: string[] = [];

  await Promise.all(
    Object.entries(manifest.inputs).map(async ([key, input]) => {
      let actualHash: string;
      try {
        actualHash = await sha256Hex(input.path);
      } catch {
        missing.push(key);
        return;
      }
      if (actualHash !== input.sha256) {
        mismatched.push(key);
      }
    }),
  );

  return { mismatched, missing };
}

// ── method 별 실행 ────────────────────────────────────────────────────────────

/**
 * design_sdm_primers 실행.
 * params 에서 알려진 키만 store 에 적용하고, 미지원 키는 무시한다.
 * 파일 로딩(loadSequence)이 완료된 뒤 designPrimers 를 호출한다.
 */
async function runDesignSdmPrimers(manifest: RunManifest): Promise<void> {
  const store = useAppStore.getState();
  const params = manifest.params;

  // 입력 파일: reference_fasta → loadSequence
  const refInput = manifest.inputs["reference_fasta"];
  if (refInput?.path) {
    await store.loadSequence(refInput.path);
  }

  // params 매핑 (알려진 키만)
  if (typeof params["mutation_text"] === "string") {
    store.setMutationText(params["mutation_text"]);
  }

  // 마지막에 design 실행
  await store.designPrimers();
}

/**
 * merge_for_evolvepro 실행.
 * active_round_id 없이는 실행 불가 → 사용자에게 에러 메시지 반환.
 */
async function runMergeForEvolvepro(manifest: RunManifest): Promise<void> {
  const activityStore = useActivityStore();
  const params = manifest.params;

  // round_id 는 params 에 있어야 한다
  const roundId = typeof params["round_id"] === "string" ? params["round_id"] : null;
  if (!roundId) {
    throw new Error(
      i18next.t("reRun.noRoundId"),
    );
  }

  // mergeForEvolvepro options (두 번째 인자는 optional)
  const options: {
    prev_round_evolvepro?: Record<string, number>;
    authoritative_measurements?: Record<string, number[]>;
    fallback_measurements?: Record<string, number[]>;
    mismatch_threshold?: number;
    ref_seq?: string;
  } = {};

  if (typeof params["mismatch_threshold"] === "number") {
    options.mismatch_threshold = params["mismatch_threshold"];
  }
  if (typeof params["ref_seq"] === "string") {
    options.ref_seq = params["ref_seq"];
  }

  await activityStore.getState().mergeForEvolvepro(roundId, options);
}

// ── 공개 API ─────────────────────────────────────────────────────────────────

/**
 * manifest 를 기반으로 적절한 store action 을 실행한다.
 *
 * export 전용 method 는 Error 를 throw 한다 (호출자가 catch + 안내).
 * 미지원 method 도 Error 를 throw 한다.
 */
export async function reRunFromManifest(manifest: RunManifest): Promise<void> {
  if (EXPORT_ONLY_METHODS.has(manifest.method)) {
    throw new Error(
      i18next.t("reRun.exportNotRunnable", { method: manifest.method }),
    );
  }

  if (!RUNNABLE_METHODS.has(manifest.method)) {
    throw new Error(
      i18next.t("reRun.unsupportedMethod", { method: manifest.method, supported: [...RUNNABLE_METHODS].join(", ") }),
    );
  }

  if (manifest.method === "design_sdm_primers") {
    await runDesignSdmPrimers(manifest);
    return;
  }

  if (manifest.method === "merge_for_evolvepro") {
    await runMergeForEvolvepro(manifest);
    return;
  }
}

// ── DnD 통합 헬퍼 ────────────────────────────────────────────────────────────

export interface ManifestDropResult {
  /** manifest 로드 성공 여부 */
  handled: boolean;
  /** 로드된 manifest (handled=true 시 존재) */
  manifest?: RunManifest;
  /** 로드 실패 시 에러 메시지 */
  error?: string;
}

/**
 * DnD drop 핸들러에서 호출하는 진입점.
 *
 * paths 배열에서 `.run.json` 또는 `run.json` 파일을 찾고,
 * 있으면 loadManifestFromFile 로 로드한 뒤 결과를 반환한다.
 * manifest 파일이 없으면 `handled: false` 를 반환하여 기존 DnD 흐름으로 fallthrough.
 *
 * @example
 * const result = await tryHandleManifestDrop(paths);
 * if (result.handled) {
 *   if (result.error) { showError(result.error); return; }
 *   openConfirmModal(result.manifest!);
 *   return; // 기존 흐름 중단
 * }
 * // 기존 흐름 계속
 */
export async function tryHandleManifestDrop(paths: string[]): Promise<ManifestDropResult> {
  const manifestPath = paths.find(isManifestPath);
  if (!manifestPath) {
    return { handled: false };
  }

  try {
    const manifest = await loadManifestFromFile(manifestPath);
    return { handled: true, manifest };
  } catch (err) {
    return { handled: true, error: String(err) };
  }
}

// ── 2개 manifest diff DnD 헬퍼 ───────────────────────────────────────────────

export interface TwoManifestDropResult {
  /** 정확히 2개 manifest 감지 여부 */
  handled: boolean;
  /** 첫 번째 manifest */
  manifestA?: RunManifest;
  /** 두 번째 manifest */
  manifestB?: RunManifest;
  /** 로드 실패 시 에러 메시지 */
  error?: string;
}

/**
 * DnD drop 핸들러에서 정확히 2개의 manifest 파일이 동시 드롭됐을 때 호출한다.
 *
 * paths 배열에서 manifest 경로를 모두 수집하고:
 *   - 2개인 경우만 handled: true 반환 (diff 흐름으로 진입)
 *   - 1개 이하거나 3개 이상이면 handled: false (기존 단일 흐름으로 fallthrough)
 *
 * 호출 순서 권장:
 *   1. tryHandleTwoManifestsDrop → handled 이면 diff dialog
 *   2. tryHandleManifestDrop    → handled 이면 re-run dialog
 *   3. 기존 파일 처리 흐름
 */
export async function tryHandleTwoManifestsDrop(
  paths: string[],
): Promise<TwoManifestDropResult> {
  const manifestPaths = paths.filter(isManifestPath);
  if (manifestPaths.length !== 2) {
    return { handled: false };
  }

  try {
    const [manifestA, manifestB] = await Promise.all([
      loadManifestFromFile(manifestPaths[0]),
      loadManifestFromFile(manifestPaths[1]),
    ]);
    return { handled: true, manifestA, manifestB };
  } catch (err) {
    return { handled: true, error: String(err) };
  }
}
