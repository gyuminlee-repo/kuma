/**
 * autosaveSnapshot.ts — mame 자동 저장 스냅샷 직렬화 (순수 함수)
 *
 * 저장 대상: 사용자가 입력한 경로/파라미터와 화면에 표시되는 안정적인 결과 상태.
 */

import type { AutosaveSnapshot } from "@/lib/autosave";
import { toPathRef, type StoredPath } from "@/lib/pathRef";
import type { AppState } from "@/store/mame/types";
import type { RawRunParams } from "@/store/mame/slice-interfaces";
import type { Round } from "@/types/round";

export const MAME_SCHEMA = 4;

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
  | "verdicts"
  | "replicates"
  | "summary"
  | "distributionStats"
  | "wells"
  | "selectedWell"
  | "runHealth"
  | "buildEvolveproCompletion"
  | "demuxResult"
  | "ampliconLengthEstimate"
  | "wellLayout"
>;

export interface MameRoundSnapshotState {
  rounds: Round[];
  activeRoundId: string | null;
}

export interface MameAutosaveSnapshot extends AutosaveSnapshot {
  schema: typeof MAME_SCHEMA;
  rounds?: Round[];
  active_round_id?: string | null;
  /**
   * schema 4 부터 경로를 `PathRef`(lib/pathRef.ts) 로 담는다. 프로젝트 안이면
   * 상대 경로, 밖이면 외부 참조다. 빈 값은 빈 문자열이고, 구버전 스냅샷은
   * 맨 절대 경로 문자열이라 복원 측이 두 형태를 모두 받는다.
   */
  input: {
    input_dir: StoredPath;
    expected_path: StoredPath;
    reference_path: StoredPath;
    output_path: StoredPath;
    sample_map_path: StoredPath;
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
  results?: {
    verdicts: AppState["verdicts"];
    replicates: AppState["replicates"];
    summary: AppState["summary"];
    distribution_stats: AppState["distributionStats"];
    wells: AppState["wells"];
    selected_well: AppState["selectedWell"];
    run_health: AppState["runHealth"];
    build_evolvepro_completion: AppState["buildEvolveproCompletion"];
    demux_result: AppState["demuxResult"];
    amplicon_length_estimate: AppState["ampliconLengthEstimate"];
    well_layout: AppState["wellLayout"];
  };
}

/** 빈 값은 빈 문자열 그대로 둔다. 참조로 감싸면 "없음" 이 표현되지 않는다. */
function ref(projectPath: string | null | undefined, value: string) {
  return value ? toPathRef(projectPath, value) : "";
}

export function buildMameSnapshot(
  state: MameSnapshotState,
  roundState?: MameRoundSnapshotState,
  projectPath?: string | null,
): MameAutosaveSnapshot {
  return {
    schema: MAME_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    rounds: roundState?.rounds ?? [],
    active_round_id: roundState?.activeRoundId ?? null,
    input: {
      input_dir: ref(projectPath, state.inputDir),
      expected_path: ref(projectPath, state.expectedPath),
      reference_path: ref(projectPath, state.referencePath),
      output_path: ref(projectPath, state.outputPath),
      sample_map_path: ref(projectPath, state.sampleMapPath),
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
    results: {
      verdicts: state.verdicts,
      replicates: state.replicates,
      summary: state.summary,
      distribution_stats: state.distributionStats,
      wells: state.wells,
      selected_well: state.selectedWell,
      run_health: state.runHealth,
      build_evolvepro_completion: state.buildEvolveproCompletion,
      demux_result: state.demuxResult,
      amplicon_length_estimate: state.ampliconLengthEstimate,
      well_layout: state.wellLayout,
    },
  };
}
