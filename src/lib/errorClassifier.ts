/**
 * §4 Error UX — 에러 분류 헬퍼.
 *
 * 네트워크 에러(UniProt/BLAST timeout, ECONNREFUSED 등)와
 * 기타 에러를 구분해 UI에서 아이콘·색상을 다르게 표시할 수 있도록 한다.
 */

export type ErrorKind = "network" | "validation" | "sidecar" | "unknown";

export interface ClassifiedError {
  kind: ErrorKind;
  /** 사람이 읽을 수 있는 1차 메시지 */
  message: string;
  /** Python traceback 등 상세 정보 (있을 경우) */
  details?: string;
}

/**
 * 네트워크 에러 패턴 목록.
 * JSON-RPC 에러 코드 -32001(timeout) / -32002(network) 또는
 * 메시지 키워드로 판별한다.
 */
const NETWORK_PATTERNS: RegExp[] = [
  /econnrefused/i,
  /timeout/i,
  /network\s+error/i,
  /uniprot.*fail/i,
  /blast.*fail/i,
  /alphafold.*fail/i,
  /fetch.*failed/i,
  /-32001/,
  /-32002/,
  /no route to host/i,
  /name or service not known/i,
  /connection\s+reset/i,
];

const VALIDATION_PATTERNS: RegExp[] = [
  /validation\s+error/i,
  /invalid\s+input/i,
  /parse\s+error/i,
  /-32600/,
  /-32602/,
];

const SIDECAR_PATTERNS: RegExp[] = [
  /sidecar/i,
  /rpc\s+error/i,
  /-32603/,
  /-32604/,
  /internal\s+error/i,
  /traceback/i,
];

function classifyKind(raw: string): ErrorKind {
  if (NETWORK_PATTERNS.some((p) => p.test(raw))) return "network";
  if (VALIDATION_PATTERNS.some((p) => p.test(raw))) return "validation";
  if (SIDECAR_PATTERNS.some((p) => p.test(raw))) return "sidecar";
  return "unknown";
}

/**
 * Python traceback 블록을 분리한다.
 *
 * JSON-RPC 에러 메시지는 종종
 * `<1차 메시지>\nTraceback (most recent call last):\n  ...` 형태.
 * 첫 줄(또는 Traceback 이전)을 1차 메시지로, 나머지를 details로 반환.
 */
function splitTraceback(raw: string): { primary: string; details?: string } {
  const traceIdx = raw.indexOf("Traceback (most recent call last)");
  if (traceIdx === -1) {
    return { primary: raw.trim() };
  }
  const primary = raw.slice(0, traceIdx).trim() || "An error occurred";
  const details = raw.slice(traceIdx).trim();
  return { primary, details };
}

/**
 * 에러 객체 또는 문자열을 ClassifiedError로 변환한다.
 *
 * @param err - Error 인스턴스, 문자열, 또는 unknown
 */
export function classifyError(err: unknown): ClassifiedError {
  const raw = err instanceof Error ? err.message : String(err ?? "Unknown error");
  const { primary, details } = splitTraceback(raw);
  const kind = classifyKind(raw);
  return { kind, message: primary, details };
}
