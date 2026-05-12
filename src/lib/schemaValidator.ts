/**
 * CSV 헤더 스키마 검증 유틸리티.
 *
 * 순수 함수만 포함 — 사이드 이펙트 없음.
 * 컬럼명은 strip + lowercase 정규화 후 비교.
 * BOM(﻿) 자동 제거.
 *
 * §3 Input Guards: 파일 업로드 시 sidecar 호출 전 사용자에게
 * 누락/불인식 컬럼을 명시적으로 보고하기 위해 사용한다.
 */

import i18next from "i18next";

export interface SchemaSpec {
  /** 반드시 존재해야 하는 컬럼명 목록 (소문자 정규화 후 비교). */
  required: string[];
  /** 존재해도 무방한 컬럼명 목록. 명시하지 않으면 unknown 검사 생략. */
  optional?: string[];
  /**
   * 별칭 그룹. canonical 컬럼명 → 허용 별칭 배열.
   * required 에 canonical 을 포함시키고, 실제 헤더가 별칭 중 하나를 가지면 충족으로 처리.
   *
   * 예시 (evolvepro variant 열):
   *   alternatives: { variant: ["variants", "mutation", "mutations", "mutant", "mutation_list"] }
   */
  alternatives?: Record<string, string[]>;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  missing: string[];
  unknown: string[];
}

/**
 * CSV 첫 줄(헤더 행)의 컬럼 배열을 SchemaSpec 에 따라 검증한다.
 *
 * 동작:
 * 1. 각 컬럼명을 trim + lowercase 정규화.
 * 2. required 항목마다 alternatives 포함 여부를 확인.
 * 3. optional 이 지정된 경우, required+optional+alternatives 전체에 없는 컬럼을 unknown 으로 표시.
 * 4. required 에서 누락된 항목이 하나라도 있으면 valid=false.
 */
export function validateCsvHeader(header: string[], spec: SchemaSpec): ValidationResult {
  const errors: string[] = [];
  const missing: string[] = [];
  const unknown: string[] = [];

  // 정규화: BOM(U+FEFF) 제거 + trim + lowercase
  // 리터럴 BOM 대신 유니코드 이스케이프 사용하여 파일 저장 중 BOM 소실 방지
  const normalized = header.map((col) => col.replace(/^\uFEFF/, "").trim().toLowerCase());

  // 모든 허용 컬럼 집합 구축 (unknown 검사용)
  const allowedSet = new Set<string>(spec.required);
  for (const alt of Object.values(spec.alternatives ?? {})) {
    for (const a of alt) allowedSet.add(a);
  }
  if (spec.optional) {
    for (const o of spec.optional) allowedSet.add(o);
  }

  // required 충족 여부 확인
  for (const req of spec.required) {
    const aliases = spec.alternatives?.[req] ?? [];
    const candidates = [req, ...aliases];
    const found = candidates.some((c) => normalized.includes(c));
    if (!found) {
      missing.push(req);
      const aliasNote = aliases.length > 0 ? i18next.t("schemaValidator.aliasNote", { aliases: aliases.join(", ") }) : "";
      errors.push(i18next.t("schemaValidator.missingColumn", { column: req, aliasNote }));
    }
  }

  // unknown 컬럼 표시 (optional 명시된 경우에만)
  if (spec.optional !== undefined) {
    for (const col of normalized) {
      if (!allowedSet.has(col)) {
        unknown.push(col);
      }
    }
  }

  return {
    valid: missing.length === 0,
    errors,
    missing,
    unknown,
  };
}

/**
 * CSV 텍스트의 첫 줄에서 헤더 컬럼 배열을 추출한다.
 *
 * 단순 쉼표 분리 방식. quoted CSV 내 쉼표는 처리하지 않는다
 * (헤더 행에서 quoted field 는 실무상 없음).
 * CRLF, LF 양쪽 처리.
 */
export function extractCsvHeader(csvText: string): string[] {
  const firstLine = csvText.split(/\r?\n/)[0] ?? "";
  return firstLine.split(",");
}

// ─── 사전 정의 SchemaSpec ──────────────────────────────────────────────────────

/**
 * kuro EVOLVEpro CSV 스키마.
 *
 * 출처: kuma_core/kuro/evolvepro.py VARIANT_COLUMNS / SCORE_COLUMNS
 * - variant 열 필수: 별칭 variants / mutation / mutations / mutant / mutation_list
 * - score 열 선택 (없으면 y_pred=0 처리): 검증 스킵
 */
export const EVOLVEPRO_CSV_SCHEMA: SchemaSpec = {
  required: ["variant"],
  optional: ["y_pred", "property_value", "predicted_fitness", "fitness", "score", "DMS_score"],
  alternatives: {
    variant: ["variants", "mutation", "mutations", "mutant", "mutation_list"],
  },
};

/**
 * kuro multi-evolve CSV 스키마.
 *
 * multi-evolve 모드는 일반 evolvepro CSV 와 동일한 컬럼을 허용한다.
 * 동일 spec 공유.
 */
export const MULTI_EVOLVE_CSV_SCHEMA: SchemaSpec = EVOLVEPRO_CSV_SCHEMA;

/**
 * mame activity long CSV 스키마.
 *
 * 출처: kuma_core/mame/activity/ingest_long_csv.py
 * - plate_id, well_id, value 필수
 * - replicate_idx 선택
 */
export const MAME_ACTIVITY_CSV_SCHEMA: SchemaSpec = {
  required: ["plate_id", "well_id", "value"],
  optional: ["replicate_idx"],
};
