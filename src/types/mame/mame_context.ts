/**
 * mame_context.ts, MAME 프로젝트 컨텍스트 파일 타입 정의
 *
 * mame_context.json 스키마 (위치: {project root}/mame_context.json)
 * 경로는 모두 프로젝트 루트 기준 상대 경로.
 *
 * Written by `kuma_core/mame/ingest/barcode_package.py`
 * (`_write_mame_context_json`). Keep the schema numbers here and there aligned.
 */

/** Newest schema this build writes. Schema 2 dropped the sample-map pointer. */
export const MAME_CONTEXT_SCHEMA = 2

/** Common to every schema. */
interface MameContextBase {
  schema: number
  published_at: string
  custom_barcodes_path?: string
  reference_path?: string
}

/**
 * Schema 1: carried a pointer to `sample_map_template.xlsx`, a hand-filled
 * (sample, well) sheet that stated the plate a second time.
 *
 * Still read, and only for migration: the pointer is how an existing project
 * names the file so `validate_inputs` can compare it against the computed
 * layout and say where the two disagree. It is never used to place a well.
 */
export interface MameContextV1 extends MameContextBase {
  schema: 1
  sample_map_template_path?: string
}

/**
 * Schema 2: no sample map. The plate is computed from the variant list plus
 * the fill rule, so there is no second file to keep in step.
 */
export interface MameContextV2 extends MameContextBase {
  schema: 2
}

export type MameContext = MameContextV1 | MameContextV2 | MameContextBase

export function isMameContext(x: unknown): x is MameContext {
  if (typeof x !== "object" || x === null || !("schema" in x)) return false
  return typeof (x as MameContextBase).schema === "number"
}

/**
 * Does this context predate the sample-map removal, and name a file to migrate?
 *
 * The schema number is the test, not the presence of the key. A schema-2 file
 * has no pointer because the project has no sample map; a schema-1 file with no
 * pointer was written before the pointer existed. Reading "key absent" as "no
 * sample map" would conflate the two, and only one of them means there is
 * nothing on disk to reconcile.
 *
 * `isMameContext` checking only `typeof schema === "number"` is why this is a
 * separate function: bumping the number does not on its own change any branch,
 * so the branch has to name the version it cares about.
 *
 * This pointer is the ONLY discovery path, and that is a decision rather than
 * an oversight. A folder assembled by hand carries no `mame_context.json`, so a
 * sample map sitting in it is never found and never compared. The alternative
 * is filename matching, which is what used to run and what picked up
 * `mutants.xlsx` as a sample map: nothing in such a folder states which
 * workbook is which, so any automatic answer is the same guess that was just
 * removed. The comparison itself stays reachable through the
 * `legacy_sample_map_xlsx` parameter (see `docs/inputs/barcodes.md`).
 */
export function legacySampleMapPointer(context: MameContext): string | null {
  if (context.schema >= MAME_CONTEXT_SCHEMA) return null
  const pointer = (context as MameContextV1).sample_map_template_path
  return typeof pointer === "string" && pointer ? pointer : null
}
