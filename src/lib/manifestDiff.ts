/**
 * manifestDiff.ts — §12 Reproducibility: 두 RunManifest 간 diff 연산
 *
 * diffManifests(a, b) 는 4개 섹션으로 나뉜 DiffEntry 배열을 반환한다.
 *
 * ─ 섹션 분류 ──────────────────────────────────────────────────────────────
 *   meta    : schema_version, method, kuma_version, kuro_module_version,
 *             python_version, platform, seed
 *   inputs  : inputs.{key}.path / sha256 / size_bytes  (키 합집합 순회)
 *   params  : params 재귀 walk — 중첩 객체는 leaf 단위로 dot-notation 전개
 *   timing  : started_at, finished_at, duration_seconds
 *
 * ─ 배열 처리 ─────────────────────────────────────────────────────────────
 *   params 안의 배열(예: excluded_ranges)은 인덱스 단위로 비교한다.
 *   배열 길이가 다르거나 요소 타입이 객체면 leaf 까지 재귀한다.
 *   배열 요소가 primitive 면 해당 인덱스를 leaf path 로 간주한다.
 *
 * 관련: docs/standards/common-frontend-standards.md §12
 */

import type { RunManifest, RunManifestInput } from "@/lib/runManifest";

// ── 공개 타입 ─────────────────────────────────────────────────────────────────

export type DiffStatus = "added" | "removed" | "changed" | "same";

export interface DiffEntry {
  /** dot-notation 경로. 예: "params.tol_max", "inputs.reference_fasta.sha256" */
  path: string;
  /** manifest A 의 값 (removed 면 A 에만 존재) */
  left: unknown;
  /** manifest B 의 값 (added 면 B 에만 존재) */
  right: unknown;
  status: DiffStatus;
}

export interface ManifestDiffResult {
  meta: DiffEntry[];
  inputs: DiffEntry[];
  params: DiffEntry[];
  timing: DiffEntry[];
}

// ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

const MISSING = Symbol("MISSING");
type MissingType = typeof MISSING;

/**
 * 두 unknown 값을 재귀적으로 walk 하여 leaf 에서만 DiffEntry 를 생성한다.
 *
 * - primitive (string | number | boolean | null) : 즉시 비교
 * - 배열 : 인덱스 단위 재귀
 * - 객체 : 키 합집합 재귀
 *
 * 키 정렬 후 JSON.stringify 대신 재귀 비교를 사용하여 키 순서 의존을 피한다.
 */
function walkDiff(
  prefix: string,
  left: unknown | MissingType,
  right: unknown | MissingType,
  out: DiffEntry[],
): void {
  const leftMissing = left === MISSING;
  const rightMissing = right === MISSING;

  // 한쪽만 있는 경우
  if (leftMissing && !rightMissing) {
    out.push({ path: prefix, left: undefined, right: right as unknown, status: "added" });
    return;
  }
  if (!leftMissing && rightMissing) {
    out.push({ path: prefix, left: left as unknown, right: undefined, status: "removed" });
    return;
  }
  if (leftMissing && rightMissing) return;

  const l = left as unknown;
  const r = right as unknown;

  // null 처리 (typeof null === "object" 이므로 먼저)
  if (l === null || r === null) {
    out.push({ path: prefix, left: l, right: r, status: l === r ? "same" : "changed" });
    return;
  }

  // 배열
  if (Array.isArray(l) || Array.isArray(r)) {
    const la = Array.isArray(l) ? l : [];
    const ra = Array.isArray(r) ? r : [];
    const len = Math.max(la.length, ra.length);
    for (let i = 0; i < len; i++) {
      const childPath = `${prefix}[${i}]`;
      const lv: unknown | MissingType = i < la.length ? la[i] : MISSING;
      const rv: unknown | MissingType = i < ra.length ? ra[i] : MISSING;
      walkDiff(childPath, lv, rv, out);
    }
    return;
  }

  // 객체 (non-null)
  if (typeof l === "object" && typeof r === "object") {
    const lo = l as Record<string, unknown>;
    const ro = r as Record<string, unknown>;
    const keys = new Set([...Object.keys(lo), ...Object.keys(ro)]);
    for (const key of keys) {
      const childPath = prefix ? `${prefix}.${key}` : key;
      const lv: unknown | MissingType = key in lo ? lo[key] : MISSING;
      const rv: unknown | MissingType = key in ro ? ro[key] : MISSING;
      walkDiff(childPath, lv, rv, out);
    }
    return;
  }

  // primitive
  out.push({ path: prefix, left: l, right: r, status: l === r ? "same" : "changed" });
}

/** 두 scalar 값을 단일 DiffEntry 로 변환한다. */
function scalarEntry(
  path: string,
  left: unknown,
  right: unknown,
): DiffEntry {
  const status: DiffStatus =
    left === undefined && right !== undefined ? "added"
    : left !== undefined && right === undefined ? "removed"
    : left === right ? "same"
    : "changed";
  return { path, left, right, status };
}

// ── inputs 섹션 diff ──────────────────────────────────────────────────────────

function diffInputs(
  a: Record<string, RunManifestInput>,
  b: Record<string, RunManifestInput>,
): DiffEntry[] {
  const out: DiffEntry[] = [];
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);

  for (const key of keys) {
    const aEntry = a[key];
    const bEntry = b[key];

    if (!aEntry && bEntry) {
      // 키 전체가 B 에만 있음 → added
      out.push({ path: `inputs.${key}.path`, left: undefined, right: bEntry.path, status: "added" });
      out.push({ path: `inputs.${key}.sha256`, left: undefined, right: bEntry.sha256, status: "added" });
      out.push({ path: `inputs.${key}.size_bytes`, left: undefined, right: bEntry.size_bytes, status: "added" });
      continue;
    }
    if (aEntry && !bEntry) {
      // 키 전체가 A 에만 있음 → removed
      out.push({ path: `inputs.${key}.path`, left: aEntry.path, right: undefined, status: "removed" });
      out.push({ path: `inputs.${key}.sha256`, left: aEntry.sha256, right: undefined, status: "removed" });
      out.push({ path: `inputs.${key}.size_bytes`, left: aEntry.size_bytes, right: undefined, status: "removed" });
      continue;
    }
    if (aEntry && bEntry) {
      out.push(scalarEntry(`inputs.${key}.path`, aEntry.path, bEntry.path));
      out.push(scalarEntry(`inputs.${key}.sha256`, aEntry.sha256, bEntry.sha256));
      out.push(scalarEntry(`inputs.${key}.size_bytes`, aEntry.size_bytes, bEntry.size_bytes));
    }
  }

  return out;
}

// ── params 섹션 diff ──────────────────────────────────────────────────────────

function diffParams(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): DiffEntry[] {
  const out: DiffEntry[] = [];
  walkDiff("params", a, b, out);
  // walkDiff 가 "params.xxx" 형태로 생성하므로 prefix 포함됨
  return out;
}

// ── 공개 API ─────────────────────────────────────────────────────────────────

/**
 * 두 RunManifest 를 비교하여 4개 섹션으로 분류된 DiffEntry 목록을 반환한다.
 *
 * 각 섹션:
 *   - meta    : 메타 필드 (method, version, platform 등)
 *   - inputs  : 입력 파일 (키 합집합, path/sha256/size_bytes 단위)
 *   - params  : 파라미터 (재귀 leaf 비교)
 *   - timing  : 시간 정보 (started_at, finished_at, duration_seconds)
 */
export function diffManifests(
  a: RunManifest,
  b: RunManifest,
): ManifestDiffResult {
  // ── meta ────────────────────────────────────────────────────────────────
  const meta: DiffEntry[] = [
    scalarEntry("schema_version", a.schema_version, b.schema_version),
    scalarEntry("method", a.method, b.method),
    scalarEntry("kuma_version", a.kuma_version, b.kuma_version),
    scalarEntry("kuro_module_version", a.kuro_module_version, b.kuro_module_version),
    scalarEntry("python_version", a.python_version, b.python_version),
    scalarEntry("platform", a.platform, b.platform),
    scalarEntry("seed", a.seed, b.seed),
  ];

  // ── inputs ──────────────────────────────────────────────────────────────
  const inputs = diffInputs(a.inputs, b.inputs);

  // ── params ──────────────────────────────────────────────────────────────
  const params = diffParams(a.params, b.params);

  // ── timing ──────────────────────────────────────────────────────────────
  const timing: DiffEntry[] = [
    scalarEntry("started_at", a.started_at, b.started_at),
    scalarEntry("finished_at", a.finished_at, b.finished_at),
    scalarEntry("duration_seconds", a.duration_seconds, b.duration_seconds),
  ];

  return { meta, inputs, params, timing };
}
