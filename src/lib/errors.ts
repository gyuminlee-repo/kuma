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
