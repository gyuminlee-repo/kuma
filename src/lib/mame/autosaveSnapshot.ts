/**
 * autosaveSnapshot.ts — mame 자동 저장 스냅샷 직렬화 (순수 함수)
 *
 * 저장 대상: inputSlice.ts saveWorkspace (라인 121-141) 기준 필드만.
 * 제외: verdicts, replicates, summary, wells, validationErrors 등 결과물 필드.
 */

import type { AutosaveSnapshot } from "@/lib/autosave";
import type { AppState } from "@/store/mame/types";
import type { RawRunParams } from "@/store/mame/slice-interfaces";

export const MAME_SCHEMA = 2;

/** buildMameSnapshot에 전달하는 상태 서브셋. AppState의 입력 필드만 포함. */
export type MameSnapshotState = Pick<
  AppState,
  | "inputDir"
  | "expectedPath"
  | "referencePath"
  | "outputPath"
  | "sampleMapPath"
  | "mode"
  | "ingestMode"
  | "inputMode"
  | "rawRunParams"
  | "cdsStart"
  | "cdsEnd"
  | "minFileSizeKb"
  | "manyCutoff"
>;

export interface MameAutosaveSnapshot extends AutosaveSnapshot {
  schema: typeof MAME_SCHEMA;
  input: {
    input_dir: string;
    expected_path: string;
    reference_path: string;
    output_path: string;
    sample_map_path: string;
  };
  parameters: {
    mode: string;
    ingest_mode: string;
    input_mode: string;
    raw_run_params: RawRunParams;
    cds_start: number;
    cds_end: number;
    min_file_size_kb: number;
    many_cutoff: number;
  };
}

/**
 * mame store 입력 상태를 AutosaveSnapshot으로 직렬화.
 * 결과물 필드(verdicts, replicates, summary, wells 등)는 포함하지 않는다.
 */
export function buildMameSnapshot(state: MameSnapshotState): MameAutosaveSnapshot {
  return {
    schema: MAME_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    input: {
      input_dir: state.inputDir,
      expected_path: state.expectedPath,
      reference_path: state.referencePath,
      output_path: state.outputPath,
      sample_map_path: state.sampleMapPath,
    },
    parameters: {
      mode: state.mode,
      ingest_mode: state.ingestMode,
      input_mode: state.inputMode,
      raw_run_params: state.rawRunParams,
      cds_start: state.cdsStart,
      cds_end: state.cdsEnd,
      min_file_size_kb: state.minFileSizeKb,
      many_cutoff: state.manyCutoff,
    },
  };
}
