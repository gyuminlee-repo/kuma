/**
 * §19 Performance Guardrails — 입력 크기 사전 경고 상수 및 체크 함수
 *
 * 임계 초과 시 UI가 AlertDialog를 표시하고 사용자 confirm 후 실행.
 * 완전 차단은 하지 않음 — level "warn"/"block" 모두 continue 버튼 제공.
 */

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
  if (seconds < 60) return `약 ${Math.ceil(seconds)}초 소요 예상`;
  const minutes = Math.ceil(seconds / 60);
  return `약 ${minutes}분 소요 예상`;
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
      message: `입력 크기가 매우 큽니다 (mutations: ${rowCount}행${fastaWarning}). ${formatEstimate(estimatedSeconds)} (예상값). 계속하면 실행 시간이 매우 길 수 있습니다.`,
      estimatedSeconds,
    };
  }

  if (rowCount >= KURO_INPUT_THRESHOLDS.ROW_WARN || (fastaMb !== undefined && fastaMb > KURO_INPUT_THRESHOLDS.FASTA_WARN_MB)) {
    return {
      level: "warn",
      message: `입력 크기가 큽니다 (mutations: ${rowCount}행${fastaWarning}). ${formatEstimate(estimatedSeconds)} (예상값).`,
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
      message: `활성 데이터 크기가 매우 큽니다 (${rowCount}행). ${formatEstimate(estimatedSeconds)} (예상값). 계속하면 실행 시간이 매우 길 수 있습니다.`,
      estimatedSeconds,
    };
  }

  if (rowCount >= MAME_INPUT_THRESHOLDS.ROW_WARN) {
    return {
      level: "warn",
      message: `활성 데이터가 큽니다 (${rowCount}행). ${formatEstimate(estimatedSeconds)} (예상값).`,
      estimatedSeconds,
    };
  }

  return { level: "ok", message: "", estimatedSeconds };
}
