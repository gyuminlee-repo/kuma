/**
 * autosaveSnapshot.ts — mame 자동 저장 스냅샷 직렬화 (순수 함수)
 *
 * 저장 대상: 사용자가 입력한 경로/파라미터와 화면에 표시되는 안정적인 결과 상태.
 */

import type { AutosaveSnapshot } from "@/lib/autosave";
import type { AppState } from "@/store/mame/types";
import type { RawRunParams } from "@/store/mame/slice-interfaces";
import type { Round } from "@/types/round";

export const MAME_SCHEMA = 3;

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

export function buildMameSnapshot(
  state: MameSnapshotState,
  roundState?: MameRoundSnapshotState,
): MameAutosaveSnapshot {
  return {
    schema: MAME_SCHEMA,
    saved_at: new Date().toISOString(),
    kuma_version: __APP_VERSION__,
    rounds: roundState?.rounds ?? [],
    active_round_id: roundState?.activeRoundId ?? null,
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
