/**
 * 에러 형식 판별 헬퍼.
 *
 * JSON-RPC 에러 코드 -32004 (ExportBlocked) 또는
 * "Export blocked"로 시작하는 메시지를 감지.
 *
 * Tauri invoke는 에러를 문자열로 반환한다.
 * formatError()가 err.message 또는 String(err)를 반환하므로
 * 메시지 문자열 기준으로 판별.
 */

/** ExportBlocked 에러인지 판별한다. */
export function isExportBlockedError(message: string): boolean {
  return (
    message.includes("-32004") ||
    /^export blocked/i.test(message.trim())
  )
}

/**
 * JSON-RPC 에러를 사용자 친화적 i18n 키 또는 메시지로 변환.
 *
 * 반환값: i18n 키 문자열 (caller가 t()로 번역) 또는 원본 메시지.
 * -32601 Method not found는 사이드카가 구버전임을 의미 → rebuild 안내 키 반환.
 *
 * @param err - JSON-RPC 에러 객체 또는 임의의 throw 값
 * @param kind - "kuro" 또는 "mame" 사이드카 종류
 */
export function describeRpcError(
  err: unknown,
  kind: "kuro" | "mame",
): string {
  // 메시지·코드 추출
  let code: number | undefined;
  let message = "";
  if (err && typeof err === "object") {
    const e = err as { code?: unknown; message?: unknown };
    if (typeof e.code === "number") code = e.code;
    if (typeof e.message === "string") message = e.message;
  } else if (typeof err === "string") {
    message = err;
  } else if (err == null) {
    message = "";
  } else {
    message = String(err);
  }

  // -32601 Method not found 감지 (code 또는 message 문자열 모두 지원)
  const isMethodNotFound =
    code === -32601 ||
    message.includes("-32601") ||
    /method not found/i.test(message);

  if (isMethodNotFound) {
    return `errors.sidecar.methodNotFound.${kind}`;
  }

  return message || "unknown error";
}
