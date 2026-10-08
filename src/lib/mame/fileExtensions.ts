/**
 * MAME 입력 파일 확장자 집합, 사이드카 정본의 단일 TS 사본.
 *
 * 정본: python-core/sidecar_mame/core.py
 *   _ALLOWED_FASTA_EXTENSIONS / _ALLOWED_SEQUENCE_EXTENSIONS / _ALLOWED_EXCEL_EXTENSIONS
 *
 * 이 집합은 `handle_validate_inputs` 가 실제로 거부/수락하는 경계다. 프런트가
 * 별도 목록을 들고 있으면 두 방향으로 어긋난다. 넓으면 picker 가 함정이 되어
 * 조작자가 고른 뒤에야 사이드카 거부가 오고("Unsupported file extension '.csv'"),
 * 좁으면 백엔드가 받는 파일을 UI 가 숨긴다(.gb reference 가 배너에서 보이지 않음).
 * 그래서 picker, 배너, 드롭 핸들러가 전부 여기서 import 한다.
 *
 * 정합은 `.cross-layer-sync.json` 의 `mame-extensions` check 가 강제한다
 * (scripts/sync-check-mame-extensions.mjs).
 *
 * 필드별 대응 (python-core/sidecar_mame/handlers/analyze.py 호출부 기준):
 *   reference        -> SEQUENCE (analyze.py:1045, 1214)
 *   expected         -> EXCEL    (analyze.py:1055, 1225)
 *   custom_barcodes  -> EXCEL    (analyze.py:1013)
 */

/** FASTA 전용. reference 가 FASTA 계열인지 판정하는 데 쓴다. */
export const MAME_FASTA_EXTENSIONS = [".fa", ".fasta", ".fna"] as const;

/** reference 로 받을 수 있는 전체 집합 (FASTA + GenBank + SnapGene). */
export const MAME_SEQUENCE_EXTENSIONS = [
  ".fa",
  ".fasta",
  ".fna",
  ".gb",
  ".gbk",
  ".gbff",
  ".dna",
] as const;

/** expected variant list 와 custom barcode 워크북. */
export const MAME_EXCEL_EXTENSIONS = [".xlsx"] as const;

/**
 * Tauri `open()` 의 `filters[].extensions` 는 점 없는 형태를 받는다.
 * 손으로 두 벌을 적으면 수정 안에서 같은 버그가 재발하므로 파생시킨다.
 */
export function toDialogExtensions(extensions: readonly string[]): string[] {
  return extensions.map((e) => (e.startsWith(".") ? e.slice(1) : e));
}

/** 소문자 확장자(점 포함) 집합 멤버십 판정. */
export function hasExtension(path: string, extensions: readonly string[]): boolean {
  const dot = path.lastIndexOf(".");
  if (dot === -1) return false;
  const ext = path.slice(dot).toLowerCase();
  return extensions.includes(ext);
}
