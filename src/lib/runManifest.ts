/**
 * runManifest.ts — §12 Reproducibility: run manifest 타입 + 로더
 *
 * 백엔드 `kuma_core/shared/run_manifest.py` 와 스키마를 공유한다.
 * `SCHEMA_VERSION` 상수를 이 파일 한 곳에만 정의하며,
 * 백엔드 schema_version 변경 시 이 상수도 동기화해야 한다.
 *
 * 관련: docs/standards/common-frontend-standards.md §12
 */

import { readTextFile } from "@tauri-apps/plugin-fs";

// ── 스키마 버전 (backend 동기화 단일 포인트) ─────────────────────────────────
export const SCHEMA_VERSION = "1.0";

// ── 입력 파일 메타 ────────────────────────────────────────────────────────────

export interface RunManifestInput {
  /** 절대 경로 */
  path: string;
  /** SHA-256 hex digest */
  sha256: string;
  /** 파일 크기 (bytes) */
  size_bytes: number;
}

// ── manifest 루트 타입 ────────────────────────────────────────────────────────

export interface RunManifest {
  schema_version: string;
  /** 백엔드 RPC method 이름 */
  method: string;
  kuma_version: string;
  kuro_module_version?: string;
  python_version: string;
  /** "linux" | "macos" | "win32" */
  platform: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  inputs: Record<string, RunManifestInput>;
  params: Record<string, unknown>;
  seed: number | null;
  extra?: Record<string, unknown>;
}

// ── type guard ────────────────────────────────────────────────────────────────

/**
 * value 가 RunManifest 구조인지 확인하는 type guard.
 * 필수 최상위 필드만 검사한다 (과도한 재귀 검증 회피).
 */
export function isRunManifest(value: unknown): value is RunManifest {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v["schema_version"] === "string" &&
    typeof v["method"] === "string" &&
    typeof v["kuma_version"] === "string" &&
    typeof v["python_version"] === "string" &&
    typeof v["platform"] === "string" &&
    typeof v["started_at"] === "string" &&
    typeof v["finished_at"] === "string" &&
    typeof v["duration_seconds"] === "number" &&
    typeof v["inputs"] === "object" &&
    v["inputs"] !== null &&
    typeof v["params"] === "object" &&
    v["params"] !== null &&
    (v["seed"] === null || typeof v["seed"] === "number")
  );
}

// ── 로더 ─────────────────────────────────────────────────────────────────────

/**
 * Tauri plugin-fs 로 경로를 읽고 JSON 파싱 + 스키마 검증을 수행한다.
 *
 * @throws 파일 읽기 실패, JSON 파싱 오류, 스키마 불일치 시 Error
 */
export async function loadManifestFromFile(path: string): Promise<RunManifest> {
  let text: string;
  try {
    text = await readTextFile(path);
  } catch (cause) {
    throw new Error(`manifest 파일을 읽을 수 없습니다: ${path}\n${String(cause)}`);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch (cause) {
    throw new Error(`manifest JSON 파싱 실패: ${path}\n${String(cause)}`);
  }

  if (!isRunManifest(parsed)) {
    throw new Error(
      `manifest 구조가 올바르지 않습니다. 필수 필드가 누락되었을 수 있습니다: ${path}`,
    );
  }

  if (parsed.schema_version !== SCHEMA_VERSION) {
    throw new Error(
      `지원하지 않는 manifest schema_version: "${parsed.schema_version}". ` +
        `현재 지원 버전: "${SCHEMA_VERSION}". ` +
        `kuma 를 업데이트하거나, 이전 버전으로 생성된 manifest 인지 확인하세요.`,
    );
  }

  return parsed;
}
