/**
 * autosaveSnapshot.ts — mame 자동 저장 스냅샷 직렬화 (순수 함수)
 *
 * 저장 대상: 사용자가 입력한 경로/파라미터와 화면에 표시되는 안정적인 결과 상태.
 *
 * schema 4부터 `input` 블록의 경로를 프로젝트 폴더 기준 이식 가능 형태로 저장한다
 * (`lib/projectPath.ts`). 폴더 안을 가리키면 `project://` 상대 경로, 밖이면 절대
 * 경로 그대로다. 구 스냅샷은 접두사가 없어 절대 경로로 읽히므로 그대로 호환된다.
 */

import type { AutosaveSnapshot } from "@/lib/autosave";
import type { AppState } from "@/store/mame/types";
import type { RawRunParams } from "@/store/mame/slice-interfaces";
import type { Round } from "@/types/round";
import { toPortablePath } from "@/lib/projectPath";
import { RESULT_CONTRACT } from "@/lib/mame/resultContract";

export const MAME_SCHEMA = 4;

export type MameSnapshotState = Pick<
  AppState,
  | "inputDir"
  | "expectedPath"
  | "referencePath"
  | "outputPath"
  | "selectedWells"
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
  | "layoutProvenance"
>;

export interface MameRoundSnapshotState {
  rounds: Round[];
  activeRoundId: string | null;
}

export interface MameAutosaveSnapshot extends AutosaveSnapshot {
  schema: typeof MAME_SCHEMA;
  /**
   * Revision of what an analyze run produces, carried because this snapshot also
   * restores results when the sibling result file is missing. Absent before
   * v0.15.21.
   */
  result_contract?: number;
  rounds?: Round[];
  active_round_id?: string | null;
  input: {
    input_dir: string;
    expected_path: string;
    reference_path: string;
    output_path: string;
    selected_wells: string[] | null;
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
    // Rides alongside well_layout so a restore can tell an inferred draft
    // layout apart from one the operator or a sample map actually supplied.
    // See useAutosaveHydration.ts applyMameSnapshot for the guard this feeds.
    layout_provenance: AppState["layoutProvenance"];
  };
}

/**
 * @param projectPath 경로 필드를 상대화할 기준 폴더. scratch 세션은 null이며
 *   이때 경로는 절대 경로로 남는다(옮길 대상이 애초에 없다).
 */
/**
 * raw_run_params 안의 파일 경로 두 개도 이식 가능한 형태로 바꾼다.
 *
 * 나머지 필드(임계값·길이·불리언)는 경로가 아니므로 손대지 않는다. 이 두 개만
 * 남겨 두면 프로젝트 폴더를 옮겼을 때 커스텀 바코드와 시퀀싱 요약만 조용히
 * 깨진다. 값이 비어 있으면 "미지정" 이므로 그대로 둔다(toPortablePath 가
 * 빈 문자열을 통과시킨다).
 */
function portableRawRunParams(
  params: RawRunParams,
  portable: (value: string) => string,
): RawRunParams {
  return {
    ...params,
    customBarcodesPath: portable(params.customBarcodesPath ?? ""),
    sequencingSummaryPath: portable(params.sequencingSummaryPath ?? ""),
  };
}

export function buildMameSnapshot(
  state: MameSnapshotState,
  roundState?: MameRoundSnapshotState,
  projectPath: string | null = null,
): MameAutosaveSnapshot {
  const portable = (value: string): string => toPortablePath(projectPath, value);
  return {
    schema: MAME_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    result_contract: RESULT_CONTRACT,
    rounds: roundState?.rounds ?? [],
    active_round_id: roundState?.activeRoundId ?? null,
    input: {
      input_dir: portable(state.inputDir),
      expected_path: portable(state.expectedPath),
      reference_path: portable(state.referencePath),
      output_path: portable(state.outputPath),
      selected_wells: state.selectedWells,
    },
    parameters: {
      mode: state.mode,
      ingest_mode: state.ingestMode,
      input_mode: state.inputMode,
      raw_run_params: portableRawRunParams(state.rawRunParams, portable),
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
      layout_provenance: state.layoutProvenance,
    },
  };
}
