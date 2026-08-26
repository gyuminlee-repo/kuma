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
import type { WtPlacement } from "@/types/mame/well_layout";
import { toPortablePath } from "@/lib/projectPath";
import { RESULT_CONTRACT } from "@/lib/mame/resultContract";

export const MAME_SCHEMA = 5;

export type MameSnapshotState = Pick<
  AppState,
  | "inputDir"
  | "expectedPath"
  | "referencePath"
  | "outputPath"
  | "selectedWells"
  | "wtPlacement"
  | "mode"
  | "ingestMode"
  | "inputMode"
  | "rawRunParams"
  | "cdsStart"
  | "cdsEnd"
  | "minFileSizeKb"
  | "minFilteredDepth"
  | "manyCutoff"
  | "maxConsensusNFraction"
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
  | "selectedNativeBarcodes"
  | "detectedBarcodeCount"
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
    /**
     * Control-well policy for a row-order variant list. Absent on a snapshot
     * saved before this field existed, which reads as "last_well" (the
     * backend default), so an old project restores to the placement it
     * already used.
     */
    wt_placement?: WtPlacement;
  };
  parameters: {
    mode: string;
    ingest_mode: string;
    input_mode: string;
    raw_run_params: RawRunParams;
    cds_start: number;
    cds_end: number;
    min_file_size_kb: number;
    /** Optional so schema 4 snapshots retain the store default on restore. */
    min_read_count?: number;
    many_cutoff: number;
    /** Optional so schema 4 snapshots retain the store default on restore. */
    max_consensus_n_fraction?: number;
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
    /**
     * The replicate axis these verdicts were scored on, as native_barcode
     * (`sort_barcodeNN`) names, and how many native barcodes the run folder
     * held. Filed under `results` rather than `input` because that is what they
     * are: `clearResults` drops both, so a restore that put them back with the
     * input setters would have them wiped by the very next setter call. Absent
     * on snapshots written before these fields existed, which reads as "no axis
     * stated" and leaves `missing_replicate` undecidable, the same answer those
     * runs would give today. No schema bump for that reason.
     */
    selected_native_barcodes?: AppState["selectedNativeBarcodes"];
    detected_barcode_count?: AppState["detectedBarcodeCount"];
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
      wt_placement: state.wtPlacement,
    },
    parameters: {
      mode: state.mode,
      ingest_mode: state.ingestMode,
      input_mode: state.inputMode,
      raw_run_params: portableRawRunParams(state.rawRunParams, portable),
      cds_start: state.cdsStart,
      cds_end: state.cdsEnd,
      min_file_size_kb: state.minFileSizeKb,
      min_read_count: state.minFilteredDepth,
      many_cutoff: state.manyCutoff,
      max_consensus_n_fraction: state.maxConsensusNFraction,
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
      selected_native_barcodes: state.selectedNativeBarcodes,
      detected_barcode_count: state.detectedBarcodeCount,
    },
  };
}

// ─── The review group a restore has to decide at once ─────────────────────
//
// The `results` object literal above writes these six unconditionally, and the
// interface types them as required, so a snapshot either has all six or was not
// written by this build. The 2.2 review screen reads them as one answer:
// `MameDrawerContent.tsx` prints `summary?.pass_count ?? 0` next to the verdict
// table, so a snapshot carrying verdicts without its summary renders "PASS: 0"
// above a table of PASS rows. Deciding the six one `if` at a time is what makes
// that state reachable, so the decision lives here, beside the writer. A reader
// that restates the tuple by hand drifts from it on the next field added.
//
// The other members of the literal are deliberately NOT in this group. A
// consumer reading `demux_result` or `well_layout` reads it on its own terms,
// not against the verdicts, and each already carries a guard whose reasoning is
// written where it is used (see `applyMameSnapshot`).

/** The six fields the 2.2 review screen reads as one answer. */
export interface MameReviewResults {
  verdicts: AppState["verdicts"];
  replicates: AppState["replicates"];
  summary: AppState["summary"];
  distributionStats: AppState["distributionStats"];
  wells: AppState["wells"];
  runHealth: AppState["runHealth"];
}

export type MameGroupRead =
  | { ok: true; value: MameReviewResults }
  | { ok: false; missing: string[] };

/**
 * A member that the store types as `X | null`.
 *
 * `null` is a value here, not an absence: `summary: null` means "not stated",
 * which is what a run that produced no summary genuinely reports. What must not
 * pass is a key that is absent or holds something that is neither. The sibling
 * array members get the opposite rule for the same reason, their store type
 * (`VerdictRecord[]`, never null) has no "not stated" reading, so a JSON `null`
 * there is corruption rather than an answer.
 */
function isNullableRecord(container: Record<string, unknown>, key: string): boolean {
  if (!(key in container)) return false;
  const value = container[key];
  if (value === null) return true;
  return typeof value === "object" && !Array.isArray(value);
}

/**
 * Read the review group whole. `missing` names every member that failed, so the
 * caller can say which part of the run did not come back.
 */
export function readMameReviewResults(results: unknown): MameGroupRead {
  const record =
    results !== null && typeof results === "object"
      ? (results as Record<string, unknown>)
      : {};
  const missing: string[] = [];
  if (!Array.isArray(record.verdicts)) missing.push("verdicts");
  if (!Array.isArray(record.replicates)) missing.push("replicates");
  if (!Array.isArray(record.wells)) missing.push("wells");
  if (!isNullableRecord(record, "summary")) missing.push("summary");
  if (!isNullableRecord(record, "distribution_stats")) missing.push("distribution_stats");
  if (!isNullableRecord(record, "run_health")) missing.push("run_health");
  if (missing.length > 0) return { ok: false, missing };
  return {
    ok: true,
    value: {
      verdicts: record.verdicts as AppState["verdicts"],
      replicates: record.replicates as AppState["replicates"],
      summary: record.summary as AppState["summary"],
      distributionStats: record.distribution_stats as AppState["distributionStats"],
      wells: record.wells as AppState["wells"],
      runHealth: record.run_health as AppState["runHealth"],
    },
  };
}
