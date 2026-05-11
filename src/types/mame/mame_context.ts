/**
 * mame_context.ts — MAME 프로젝트 컨텍스트 파일 타입 정의
 *
 * mame_context.json 스키마 (위치: {project root}/mame_context.json)
 * 경로는 모두 프로젝트 루트 기준 상대 경로.
 */

export interface MameContext {
  schema: number
  published_at: string
  custom_barcodes_path?: string
  reference_path?: string
  sample_map_template_path?: string
}

export function isMameContext(x: unknown): x is MameContext {
  return (
    typeof x === "object" &&
    x !== null &&
    "schema" in x &&
    typeof (x as MameContext).schema === "number"
  )
}
