/**
 * §19 Performance Guardrails — input size pre-check constants and functions.
 *
 * When a threshold is exceeded, the UI shows an AlertDialog and waits for user confirm.
 * Execution is never fully blocked — both "warn" and "block" levels offer a continue button.
 */

import i18next from "i18next";

export const KURO_INPUT_THRESHOLDS = {
  /** mutation 행 수 경고 임계 */
  ROW_WARN: 1000,
  /** mutation 행 수 강권 임계 (계속하면 시간이 매우 길 수 있음) */
  ROW_BLOCK: 10000,
  /** reference fasta 파일 크기 경고 임계 (MB) */
  FASTA_WARN_MB: 50,
  /** 행당 평균 처리 시간 (초) — 추정치이므로 예상값임을 UI에 명시 */
  AVG_SECONDS_PER_ROW: 0.5,
} as const;

export const MAME_INPUT_THRESHOLDS = {
  /** activity 레코드 수 경고 임계 */
  ROW_WARN: 5000,
  /** activity 레코드 수 강권 임계 */
  ROW_BLOCK: 100000,
  /** 행당 평균 처리 시간 (초) */
  AVG_SECONDS_PER_ROW: 0.05,
} as const;

export type InputSizeLevel = "ok" | "warn" | "block";

export interface InputSizeCheckResult {
  level: InputSizeLevel;
  /** 사용자에게 노출할 메시지 (level이 "ok"이면 빈 문자열) */
  message: string;
  /** 추정 소요 초 (0이면 계산 불가) */
  estimatedSeconds: number;
}

interface KuroCheckParams {
  rowCount: number;
  fastaMb?: number;
}

interface MameCheckParams {
  rowCount: number;
}

function formatEstimate(seconds: number): string {
  if (seconds < 60) return i18next.t("inputThresholds.estimateSec", { sec: Math.ceil(seconds) });
  const minutes = Math.ceil(seconds / 60);
  return i18next.t("inputThresholds.estimateMin", { min: minutes });
}

/** kuro design 실행 전 입력 크기 검사 */
export function checkKuroInputSize({ rowCount, fastaMb }: KuroCheckParams): InputSizeCheckResult {
  const estimatedSeconds = rowCount * KURO_INPUT_THRESHOLDS.AVG_SECONDS_PER_ROW;
  const fastaWarning =
    fastaMb !== undefined && fastaMb > KURO_INPUT_THRESHOLDS.FASTA_WARN_MB
      ? `, reference ${fastaMb.toFixed(0)} MB`
      : "";

  if (rowCount >= KURO_INPUT_THRESHOLDS.ROW_BLOCK) {
    return {
      level: "block",
      message: i18next.t("inputThresholds.kuroLargeBlock", { rowCount, fastaWarning, estimate: formatEstimate(estimatedSeconds) }),
      estimatedSeconds,
    };
  }

  if (rowCount >= KURO_INPUT_THRESHOLDS.ROW_WARN || (fastaMb !== undefined && fastaMb > KURO_INPUT_THRESHOLDS.FASTA_WARN_MB)) {
    return {
      level: "warn",
      message: i18next.t("inputThresholds.kuroLargeWarn", { rowCount, fastaWarning, estimate: formatEstimate(estimatedSeconds) }),
      estimatedSeconds,
    };
  }

  return { level: "ok", message: "", estimatedSeconds };
}

/** mame activity 분석 전 입력 크기 검사 */
export function checkMameInputSize({ rowCount }: MameCheckParams): InputSizeCheckResult {
  const estimatedSeconds = rowCount * MAME_INPUT_THRESHOLDS.AVG_SECONDS_PER_ROW;

  if (rowCount >= MAME_INPUT_THRESHOLDS.ROW_BLOCK) {
    return {
      level: "block",
      message: i18next.t("inputThresholds.mameLargeBlock", { rowCount, estimate: formatEstimate(estimatedSeconds) }),
      estimatedSeconds,
    };
  }

  if (rowCount >= MAME_INPUT_THRESHOLDS.ROW_WARN) {
    return {
      level: "warn",
      message: i18next.t("inputThresholds.mameLargeWarn", { rowCount, estimate: formatEstimate(estimatedSeconds) }),
      estimatedSeconds,
    };
  }

  return { level: "ok", message: "", estimatedSeconds };
}
