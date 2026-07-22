/**
 * useAutosaveHydration.ts — Phase 4: 프로젝트 진입 시 자동 저장 파일 복원
 *
 * 프로젝트가 처음 활성화될 때 한 번만 실행된다.
 * kuro와 mame 두 스냅샷을 병렬로 읽고 각 store에 복원한다.
 * KURO는 schema 2부터 결과물 필드(designResults 등)까지 함께 복원한다.
 * MAME 결과물은 별도 result 스냅샷 경로(restoreMameResult)로 복원한다.
 */

import { useEffect, useRef } from "react";
import i18next from "i18next";
import { useKumaProject } from "@/state/projectContext";
import {
  readAutosave,
  readScratchAutosave,
  deleteScratchAutosave,
  blockAutosaveWrites,
  clearAutosaveBlock,
  beginHydration,
  endHydration,
  ensureAutosaveDir,
  autosavePath,
  atomicWriteJson,
} from "@/lib/autosave";
import { readMameResultSnapshot } from "@/lib/mame/resultSnapshot";
import { sendRequest as sendMameRequest } from "@/lib/ipc-mame";
import type { LoadAnalyzeResultResponse } from "@/types/mame/models";
import { KURO_SCHEMA, buildKuroSnapshot } from "@/lib/kuroSnapshot";
import { MAME_SCHEMA } from "@/lib/mame/autosaveSnapshot";
import { detectProjectFiles, detectFromInputDir } from "@/lib/mame/detectProjectFiles";
import { openWorkspace } from "@/lib/workspace";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { resetMameAll } from "@/store/mame/resetAll";
import type { AppState } from "@/store/appStore";
import type { AutosaveSnapshot, ReadAutosaveResult } from "@/lib/autosave";
import type { MameAutosaveSnapshot } from "@/lib/mame/autosaveSnapshot";

// ─── 공개 타입 ────────────────────────────────────────────────────────────

export interface HydrationStatusMessage {
  kind: "kuro" | "mame";
  variant: "restored" | "corrupted" | "schema_too_new" | "missing" | "io_failed";
  message: string;
  /** ISO 문자열. "5분 전" 표시용 */
  savedAt?: string;
}

// ─── 상대 시간 포맷 헬퍼 ─────────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return i18next.t("autosaveHydration.relativeJustNow");
  if (diffMin < 60) return i18next.t("autosaveHydration.relativeMinAgo", { count: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return i18next.t("autosaveHydration.relativeHrAgo", { count: diffHr });
  return i18next.t("autosaveHydration.relativeDayAgo", { count: Math.floor(diffHr / 24) });
}

// ─── Kuro 복원 ────────────────────────────────────────────────────────────

function isMutationInputMode(value: unknown): value is AppState["mutationInputMode"] {
  return value === "text" || value === "evolvepro";
}

/** Accepts the legacy "others" literal too, callers coerce it to "pipeline". */
function isEvolveproModeRaw(value: unknown): value is "topN" | "pipeline" | "others" {
  return value === "topN" || value === "pipeline" || value === "others";
}

function isScoreOrder(value: unknown): value is "asc" | "desc" {
  return value === "asc" || value === "desc";
}

function isCodonStrategy(value: unknown): value is AppState["codonStrategy"] {
  return value === "closest" || value === "optimal";
}

function isOverlapMode(value: unknown): value is AppState["overlapMode"] {
  return value === "partial" || value === "full";
}

function isDomainStrategy(value: unknown): value is AppState["domainStrategy"] {
  return value === "proportional" || value === "equal";
}

function isDomainOverlapPolicy(value: unknown): value is AppState["domainOverlapPolicy"] {
  return value === "first" || value === "largest";
}

function isLinkerHandling(value: unknown): value is AppState["linkerHandling"] {
  return value === "include" || value === "separate-bin" || value === "exclude";
}

function isDistanceMode(value: unknown): value is AppState["distanceMode"] {
  return value === "auto" || value === "1d" || value === "3d";
}

/** Exported for unit testing (legacy "others" -> "pipeline" migration path). */
export async function applyKuroSnapshot(snapshot: AutosaveSnapshot): Promise<void> {
  const input = snapshot.input as Record<string, unknown> | undefined;
  const params = snapshot.parameters as Record<string, unknown> | undefined;
  const diversity = snapshot.diversity as Record<string, unknown> | undefined;
  const patch: Partial<AppState> = {};

  // input
  if (isMutationInputMode(input?.mutation_input_mode)) {
    // Coerce legacy "text" mode to "evolvepro" (Text input removed from UI)
    patch.mutationInputMode = input.mutation_input_mode === "text" ? "evolvepro" : input.mutation_input_mode;
  }
  if (typeof input?.mutation_text === "string") {
    patch.mutationText = input.mutation_text;
  }
  if (input?.sequence_path === null) {
    patch.fastaPath = "";
    patch.seqInfo = null;
    patch.selectedGene = "";
  }
  if (typeof input?.organism === "string") {
    patch.organism = input.organism;
  }
  if (isEvolveproModeRaw(input?.evolvepro_mode)) {
    // Legacy "others" (pre-merge autosaves) coerces to "pipeline", the
    // "Others" source file is now loaded through evolveproCsvPath with
    // column-mapping overrides, not a separate mode.
    patch.evolveproMode = input.evolvepro_mode === "others" ? "pipeline" : input.evolvepro_mode;
  } else if (typeof diversity?.pipeline_mode === "boolean") {
    patch.evolveproMode = diversity.pipeline_mode ? "pipeline" : "topN";
  }
  // Legacy fallback: pre-merge autosaves wrote both evolvepro_* (real value
  // only when mode !== "others") and others_* (real value only when mode
  // === "others") unconditionally. Pick the channel that was actually
  // authoritative for the saved mode so an untouched default on the inactive
  // channel never clobbers the real override.
  const wasOthersMode = input?.evolvepro_mode === "others";
  if (wasOthersMode) {
    if (typeof input?.others_source_path === "string" || input?.others_source_path === null) {
      patch.evolveproCsvPath = input.others_source_path ?? "";
    }
    if (typeof input?.others_variant_column === "string" || input?.others_variant_column === null) {
      patch.evolveproVariantColumn = input.others_variant_column;
    }
    if (typeof input?.others_score_column === "string" || input?.others_score_column === null) {
      patch.evolveproScoreColumn = input.others_score_column;
    }
    if (isScoreOrder(input?.others_score_order)) {
      patch.evolveproScoreOrder = input.others_score_order;
    }
    if (typeof input?.others_sheet_name === "string" || input?.others_sheet_name === null) {
      patch.evolveproSheetName = input.others_sheet_name;
    }
  } else {
    if (typeof input?.evolvepro_csv_path === "string" || input?.evolvepro_csv_path === null) {
      patch.evolveproCsvPath = input.evolvepro_csv_path ?? "";
    }
    if (typeof input?.evolvepro_variant_column === "string" || input?.evolvepro_variant_column === null) {
      patch.evolveproVariantColumn = input.evolvepro_variant_column;
    }
    if (typeof input?.evolvepro_score_column === "string" || input?.evolvepro_score_column === null) {
      patch.evolveproScoreColumn = input.evolvepro_score_column;
    }
    if (isScoreOrder(input?.evolvepro_score_order)) {
      patch.evolveproScoreOrder = input.evolvepro_score_order;
    }
    if (typeof input?.evolvepro_sheet_name === "string" || input?.evolvepro_sheet_name === null) {
      patch.evolveproSheetName = input.evolvepro_sheet_name;
    }
  }

  // parameters
  if (typeof params?.polymerase === "string") {
    patch.selectedPolymerase = params.polymerase;
  }
  if (isCodonStrategy(params?.codon_strategy)) {
    patch.codonStrategy = params.codon_strategy;
  }
  if (typeof params?.max_primers === "number") {
    patch.maxPrimers = params.max_primers;
  }
  if (typeof params?.tm_fwd_target === "number") {
    patch.tmFwdTarget = params.tm_fwd_target;
  }
  if (typeof params?.tm_rev_target === "number") {
    patch.tmRevTarget = params.tm_rev_target;
  }
  if (typeof params?.tm_overlap_target === "number") {
    patch.tmOverlapTarget = params.tm_overlap_target;
  }
  if (typeof params?.gc_min === "number") {
    patch.gcMin = params.gc_min;
  }
  if (typeof params?.gc_max === "number") {
    patch.gcMax = params.gc_max;
  }
  if (typeof params?.primer_len_enabled === "boolean") {
    patch.primerLenEnabled = params.primer_len_enabled;
  }
  if (typeof params?.fwd_len_min === "number") {
    patch.fwdLenMin = params.fwd_len_min;
  }
  if (typeof params?.fwd_len_max === "number") {
    patch.fwdLenMax = params.fwd_len_max;
  }
  if (typeof params?.rev_len_min === "number") {
    patch.revLenMin = params.rev_len_min;
  }
  if (typeof params?.rev_len_max === "number") {
    patch.revLenMax = params.rev_len_max;
  }
  if (typeof params?.fill_on_failure === "boolean") {
    patch.fillOnFailure = params.fill_on_failure;
  }
  if (isOverlapMode(params?.overlap_mode)) {
    patch.overlapMode = params.overlap_mode;
  }

  // diversity
  if (Array.isArray(diversity?.domains) && Array.isArray(diversity?.disabled_domains)) {
    patch.domains = diversity.domains as AppState["domains"];
    patch.disabledDomains = diversity.disabled_domains as string[];
  }
  if (typeof diversity?.position_diversity_enabled === "boolean") {
    patch.positionDiversityEnabled = diversity.position_diversity_enabled;
  }
  if (typeof diversity?.max_per_position === "number") {
    patch.maxPerPosition = diversity.max_per_position;
  }
  if (typeof diversity?.domain_diversity_enabled === "boolean") {
    patch.domainDiversityEnabled = diversity.domain_diversity_enabled;
  }
  if (isDomainStrategy(diversity?.domain_strategy)) {
    patch.domainStrategy = diversity.domain_strategy;
  }
  if (isDomainOverlapPolicy(diversity?.domain_overlap_policy)) {
    patch.domainOverlapPolicy = diversity.domain_overlap_policy;
  }
  if (isLinkerHandling(diversity?.linker_handling)) {
    patch.linkerHandling = diversity.linker_handling;
  }
  if (typeof diversity?.domain_quota_min === "number") {
    patch.domainQuotaMin = diversity.domain_quota_min;
  }
  if (typeof input?.uniprot_accession === "string" || input?.uniprot_accession === null) {
    patch.uniprotAccession = input.uniprot_accession ?? "";
  }
  if (typeof diversity?.pareto_diversity_enabled === "boolean") {
    patch.paretoDiversityEnabled = diversity.pareto_diversity_enabled;
  }
  if (typeof diversity?.structural_diversity_enabled === "boolean") {
    patch.structuralDiversityEnabled = diversity.structural_diversity_enabled;
  }
  if (typeof diversity?.structural_kappa === "number") {
    patch.structuralKappa = Math.max(0, Math.min(1, diversity.structural_kappa));
  }
  if (typeof diversity?.entropy_weight_enabled === "boolean") {
    patch.entropyWeightEnabled = diversity.entropy_weight_enabled;
  }
  if (typeof diversity?.entropy_weight === "number") {
    patch.entropyWeight = diversity.entropy_weight;
  }
  if (typeof diversity?.pareto_pool_multiplier === "number") {
    patch.paretoPoolMultiplier = diversity.pareto_pool_multiplier;
  }
  if (isDistanceMode(diversity?.distance_mode)) {
    patch.distanceMode = diversity.distance_mode;
  }
  if (typeof diversity?.evolvepro_round === "number") {
    patch.evolveproRound = diversity.evolvepro_round;
  }
  if (typeof diversity?.round_size === "number") {
    patch.roundSize = diversity.round_size;
  }
  if (typeof diversity?.auto_redesign_on_load === "boolean") {
    patch.autoRedesignOnLoad = diversity.auto_redesign_on_load;
  }
  if (typeof diversity?.save_cache === "boolean") {
    patch.saveCache = diversity.save_cache;
  }

  if (typeof input?.sequence_path === "string" && input.sequence_path) {
    try {
      await useAppStore.getState().loadSequence(input.sequence_path);
    } catch {
      console.warn("[autosave] kuro: sequence load failed, continuing restore");
    }
  }

  const selectedCds = typeof input?.selected_cds === "string" ? input.selected_cds : "";
  if (selectedCds) {
    const state = useAppStore.getState();
    const geneExists = state.seqInfo?.genes.some((g) => String(g.cds_start) === selectedCds) ?? false;
    if (geneExists) {
      patch.selectedGene = selectedCds;
    }
  }

  // results (schema 2+). schema 1 스냅샷에는 results가 없으므로 결과물만 비어 있게 된다.
  const results = snapshot.results as Record<string, unknown> | undefined;
  if (results !== undefined) {
    if (Array.isArray(results.designResults)) {
      patch.designResults = results.designResults as AppState["designResults"];
      // 디스크에서 복원한 결과물은 사이드카 설계 상태와 무관하다.
      // 이 플래그가 true로 남으면 primer swap/alternatives가 없는 백엔드
      // 상태를 가정하고 동작한다.
      patch.backendDesignStateSynced = false;
    }
    if (typeof results.successCount === "number") {
      patch.successCount = results.successCount;
    }
    if (typeof results.totalCount === "number") {
      patch.totalCount = results.totalCount;
    }
    if (Array.isArray(results.failedMutations)) {
      patch.failedMutations = results.failedMutations as AppState["failedMutations"];
    }
    if (Array.isArray(results.plateMappings)) {
      patch.plateMappings = results.plateMappings as AppState["plateMappings"];
    }
    if (typeof results.dedupInfo === "object" && results.dedupInfo !== null) {
      patch.dedupInfo = results.dedupInfo as AppState["dedupInfo"];
    }
    if (typeof results.manuallySwapped === "object" && results.manuallySwapped !== null) {
      const safe: Record<string, "fwd" | "rev" | "both"> = {};
      for (const [k, v] of Object.entries(results.manuallySwapped)) {
        if (v === "fwd" || v === "rev" || v === "both") safe[k] = v;
      }
      patch.manuallySwapped = safe;
    }
    if (typeof results.customCandidates === "object" && results.customCandidates !== null) {
      patch.customCandidates = results.customCandidates as AppState["customCandidates"];
    }
    if (Array.isArray(results.rescuedMutationDetails)) {
      patch.rescuedMutationDetails = results.rescuedMutationDetails as AppState["rescuedMutationDetails"];
    }
  }

  useAppStore.setState(patch);

  const activeSourcePath = patch.evolveproCsvPath ?? useAppStore.getState().evolveproCsvPath;
  if (activeSourcePath) {
    try {
      await useAppStore.getState().loadEvolveproCsv(activeSourcePath);
    } catch {
      console.warn("[autosave] kuro: EVOLVEpro source load failed, continuing restore");
    }
  }
}

/**
 * 읽기 실패를 사용자에게 보여줄 문구.
 *
 * 전용 i18n 키(`autosaveHydration.readFailed`)가 아직 없고 이번 변경에서 키를
 * 추가할 수 없어, 의미가 가장 가까운 `mainShell.autosaveFailed`("Save failed")를
 * 재사용한다. 읽기 실패 시점부터 해당 kind의 자동 저장 쓰기가 실제로 봉인되므로
 * 사용자 관점에서 "저장 실패"는 참인 서술이다. 원인 추적을 위해 파일명과 원본
 * 에러 메시지를 덧붙인다.
 */
function readFailedMessage(filePath: string, error: Error): string {
  const filename = filePath.split(/[/\\]/).pop() ?? filePath;
  return `${i18next.t("mainShell.autosaveFailed")}: ${filename} (${error.message})`;
}

/**
 * scratch 자동 저장 읽기 결과를 KURO store에 반영하고 상태 메시지를 보낸다.
 * 프로젝트 스냅샷 처리와 동일한 variant 규칙(missing은 침묵)을 따른다.
 *
 * `source`는 문구만 가른다. "scratch"는 프로젝트 없이 이어서 작업하는 정상
 * 복원이고, "promotion"은 저장 안 된 세션 내용을 새 프로젝트로 물려받는
 * 경우라서 사용자가 구분할 수 있어야 한다.
 *
 * @returns 스냅샷이 실제로 store에 반영됐으면 true.
 */
async function applyScratchKuroSnapshot(
  result: ReadAutosaveResult,
  onMessage: (msg: HydrationStatusMessage) => void,
  isCurrent: () => boolean,
  source: "scratch" | "promotion" = "scratch",
): Promise<boolean> {
  if (result.status === "ok") {
    try {
      await applyKuroSnapshot(result.snapshot);
    } catch (err) {
      console.warn("[autosave] kuro scratch: apply snapshot failed", err);
      onMessage({
        kind: "kuro",
        variant: "corrupted",
        message: i18next.t("autosaveHydration.corrupted", {
          filename: "kuro-scratch-autosave.json",
        }),
      });
      return false;
    }
    // 이미 다른 프로젝트로 넘어간 복원이면 false. 승격 쓰기·scratch 삭제 같은
    // 후속 부작용이 지나간 대상에 적용되면 안 된다.
    if (!isCurrent()) return false;
    const relative = formatRelativeTime(result.snapshot.saved_at);
    // 전용 키(`autosaveHydration.carriedFromScratch`)가 없어 기존 restored 문구에
    // 기존 "Scratch" 라벨을 덧붙여 출처를 구분한다.
    const message =
      source === "promotion"
        ? `${i18next.t("autosaveHydration.restored", { relative })} (${i18next.t("mainShell.scratchSuffix")})`
        : i18next.t("autosaveHydration.restored", { relative });
    onMessage({
      kind: "kuro",
      variant: "restored",
      message,
      savedAt: result.snapshot.saved_at,
    });
    return true;
  }
  if (result.status === "read_failed") {
    // 읽지 못한 스냅샷 위에 빈 상태를 덮어쓰지 않도록 쓰기를 봉인한다.
    blockAutosaveWrites("kuro", result.error);
    onMessage({
      kind: "kuro",
      variant: "io_failed",
      message: readFailedMessage(result.filePath, result.error),
    });
    return false;
  }
  if (result.status === "corrupted") {
    onMessage({
      kind: "kuro",
      variant: "corrupted",
      message: i18next.t("autosaveHydration.corrupted", {
        filename: result.backupPath.split("/").pop() ?? "kuro-scratch-autosave.json",
      }),
    });
    return false;
  }
  if (result.status === "schema_too_new") {
    onMessage({
      kind: "kuro",
      variant: "schema_too_new",
      message: i18next.t("autosaveHydration.schemaTooNew"),
    });
  }
  // missing → 침묵
  return false;
}

/**
 * scratch 스냅샷을 프로젝트 자동 저장 파일로 확정하고 원본을 제거한다.
 *
 * 순서가 핵심이다. 프로젝트 파일 쓰기가 성공한 뒤에만 scratch 파일을 지운다.
 * 반대로 하면 쓰기 실패 시 양쪽 모두 사라진다. 삭제하지 않으면 이후 만드는
 * 모든 신규 프로젝트가 같은 scratch 내용을 다시 물려받는다.
 *
 * hydration 게이트가 살아 있는 구간이라 scheduleAutosave는 무시되므로
 * atomicWriteJson으로 직접 쓴다.
 */
async function promoteScratchToProject(projectPath: string): Promise<void> {
  await ensureAutosaveDir(projectPath);
  await atomicWriteJson(
    autosavePath(projectPath, "kuro"),
    buildKuroSnapshot(useAppStore.getState()),
  );
  await deleteScratchAutosave();
}

// ─── Mame 자동 탐지 ──────────────────────────────────────────────────────

/**
 * MAME 입력 파일 자동 탐지를 실행하고 빈 필드를 채운다.
 *
 * - mame_context.json 우선 시도 (detectProjectFiles 내부에서 처리)
 * - 이미 채워진 store 필드는 보호
 * - onMessage 콜백: 채워진 필드 목록 또는 "no new files" 전달
 *
 * Re-detect 버튼이나 외부에서 직접 호출할 수 있도록 export.
 */
export async function applyMameAutoDetect(
  projectPath: string,
  onMessage: (filled: string[]) => void,
): Promise<void> {
  const detected = await detectProjectFiles(projectPath);
  const store = useMameAppStore.getState();
  const filled: string[] = [];

  // store.inputDir가 비어있었는지 기록 (setInputDir 이전 캡처)
  const inputDirWasEmpty = !store.inputDir;

  if (inputDirWasEmpty && detected.inputDir) {
    store.setInputDir(detected.inputDir);
    filled.push(i18next.t("autosaveHydration.fieldRunFolder"));
  }
  if (!store.referencePath && detected.referencePath) {
    store.setReferencePath(detected.referencePath);
    filled.push(i18next.t("autosaveHydration.fieldReference"));
  }
  if (!store.expectedPath && detected.expectedPath) {
    store.setExpectedPath(detected.expectedPath);
    filled.push(i18next.t("autosaveHydration.fieldExpected"));
  }
  if (!store.sampleMapPath && detected.sampleMapPath) {
    store.setSampleMapPath(detected.sampleMapPath);
    filled.push(i18next.t("autosaveHydration.fieldSampleMap"));
  }
  if (!store.rawRunParams.customBarcodesPath && detected.customBarcodesPath) {
    store.setParams({ rawRunParams: { customBarcodesPath: detected.customBarcodesPath } });
    filled.push(i18next.t("autosaveHydration.fieldCustomBarcodes"));
  }
  if (!store.rawRunParams.sequencingSummaryPath && detected.sequencingSummaryPath) {
    store.setParams({ rawRunParams: { sequencingSummaryPath: detected.sequencingSummaryPath } });
    filled.push(i18next.t("autosaveHydration.fieldSequencingSummary"));
  }

  // inputDir가 비어있었고 새로 설정되었으며, inputDir ≠ projectPath 인 경우
  // — MinKNOW run 폴더 내부를 추가 스캔해 남은 빈 필드를 보충한다.
  if (inputDirWasEmpty && detected.inputDir && detected.inputDir !== projectPath) {
    const fromInputDir = await detectFromInputDir(detected.inputDir);
    const storeAfter = useMameAppStore.getState();

    if (!storeAfter.referencePath && fromInputDir.referencePath) {
      storeAfter.setReferencePath(fromInputDir.referencePath);
      filled.push(i18next.t("autosaveHydration.fieldReference"));
    }
    if (!storeAfter.expectedPath && fromInputDir.expectedPath) {
      storeAfter.setExpectedPath(fromInputDir.expectedPath);
      filled.push(i18next.t("autosaveHydration.fieldExpected"));
    }
    if (!storeAfter.sampleMapPath && fromInputDir.sampleMapPath) {
      storeAfter.setSampleMapPath(fromInputDir.sampleMapPath);
      filled.push(i18next.t("autosaveHydration.fieldSampleMap"));
    }
    if (!storeAfter.rawRunParams.customBarcodesPath && fromInputDir.customBarcodesPath) {
      storeAfter.setParams({ rawRunParams: { customBarcodesPath: fromInputDir.customBarcodesPath } });
      filled.push(i18next.t("autosaveHydration.fieldCustomBarcodes"));
    }
    if (!storeAfter.rawRunParams.sequencingSummaryPath && fromInputDir.sequencingSummaryPath) {
      storeAfter.setParams({ rawRunParams: { sequencingSummaryPath: fromInputDir.sequencingSummaryPath } });
      filled.push(i18next.t("autosaveHydration.fieldSequencingSummary"));
    }
  }

  onMessage(filled);
}

// ─── Mame 복원 ────────────────────────────────────────────────────────────

function applyMameSnapshot(snapshot: MameAutosaveSnapshot): void {
  const store = useMameAppStore.getState();
  const { input, parameters } = snapshot;

  store.setParams({
    mode: parameters.mode as Parameters<typeof store.setParams>[0]["mode"],
    ingestMode: parameters.ingest_mode as Parameters<typeof store.setParams>[0]["ingestMode"],
    inputMode: (parameters.input_mode as Parameters<typeof store.setParams>[0]["inputMode"]) ?? "raw_run",
    rawRunParams: parameters.raw_run_params ?? undefined,
    cdsStart: parameters.cds_start,
    cdsEnd: parameters.cds_end,
    minFileSizeKb: parameters.min_file_size_kb,
    manyCutoff: parameters.many_cutoff,
  });
  store.setInputDir(input.input_dir);
  store.setExpectedPath(input.expected_path);
  store.setReferencePath(input.reference_path);
  store.setOutputPath(input.output_path);
  if (input.sample_map_path) store.setSampleMapPath(input.sample_map_path);

  useMameAppStore.setState({
    validationErrors: [],
    analyzeMessage: i18next.t("autosaveHydration.workspaceRestored"),
  });
}

// ─── Mame analyze-result 복원 ──────────────────────

/**
 * Restore a persisted analyze result (sibling result file) into BOTH the
 * sidecar and the store, then land on the 2.2 review view.
 *
 * Runs AFTER the input-snapshot restore. Independent of input-snapshot status:
 * the result file alone is sufficient to repopulate verdicts/replicates and the
 * plate view. Missing result file -> silent skip (returns false).
 *
 * Sequence (locked):
 *  1. load_analyze_result RPC (re-injects sidecar SidecarState; otherwise
 *     get_plate_data throws -32002 and Plate View breaks)
 *  2. store verdicts / replicates / summary / distribution_stats
 *  3. loadPlateData() (reads get_plate_data from the restored sidecar state)
 *  4. setMameSubStep("analyze.review")
 *
 * The persisted `result.replicates[].plate_verdicts` is replayed AS-IS; it is
 * the only lossless source for per-plate accent restoration.
 */
async function restoreMameResult(projectPath: string): Promise<boolean> {
  const read = await readMameResultSnapshot(projectPath);
  if (read.status !== "ok") return false;

  const { result } = read.snapshot;
  const store = useMameAppStore.getState();

  await sendMameRequest<LoadAnalyzeResultResponse>("load_analyze_result", {
    verdicts: result.verdicts,
    replicates: result.replicates,
    output_path: result.output_path,
    summary: result.summary ?? null,
    distribution_stats: result.distribution_stats ?? null,
  });

  store.setVerdicts(result.verdicts);
  store.setReplicates(result.replicates);
  store.setSummary(result.summary);
  store.setDistributionStats(result.distribution_stats ?? null);
  await store.loadPlateData();
  // A8: the run-health panel ("Plate별 verdict 분포") reads get_run_health from the
  // restored sidecar state; without this it stays null and shows "설정 미완료".
  await store.loadRunHealth();
  store.setMameSubStep("analyze.review");
  return true;
}

// ─── 훅 ──────────────────────────────────────────────────────────────────

/**
 * 프로젝트 진입 시 kuro + mame 자동 저장 파일을 복원한다.
 *
 * - path가 null이면 즉시 종료.
 * - scratch 포함 projectPath 변경마다 이전 프로젝트의 in-memory KURO/MAME 상태를 먼저 비운다.
 * - scratch 프로젝트는 앱 데이터 디렉토리의 KURO scratch 스냅샷만 복원한다.
 * - 프로젝트 KURO 스냅샷이 없으면 scratch 스냅샷으로 폴백한다.
 * - 같은 projectPath/scratch 조합이 연속 렌더되는 경우만 중복 복원을 막는다.
 */
export function useAutosaveHydration(
  onMessage: (msg: HydrationStatusMessage) => void,
): void {
  const project = useKumaProject();
  /** 마지막으로 복원을 시작한 project key. 같은 경로/모드 연속 렌더만 중복 방지. */
  const lastHydratedKey = useRef<string | null>(null);

  useEffect(() => {
    if (!project || !project.path) return;
    const { path, scratch } = project;
    const hydrationKey = `${scratch ? "scratch" : "project"}:${path}`;
    if (lastHydratedKey.current === hydrationKey) return;
    lastHydratedKey.current = hydrationKey;

    let cancelled = false;
    const isCurrent = () => !cancelled && lastHydratedKey.current === hydrationKey;

    // 자동 저장 스케줄을 복원이 끝날 때까지 막는다. resetAll이 새 리터럴을 넣는
    // 순간 구독자(useKuroAutosave)가 스케줄을 걸고, 그 스냅샷은 복원 전 빈
    // 상태다. loadSequence/loadEvolveproCsv는 사이드카 RPC라 디바운스 1.5초를
    // 넘길 수 있어, 게이트가 없으면 빈 스냅샷이 먼저 디스크에 착지한다.
    // 동기 호출이어야 한다. 아래 IIFE의 첫 await 전에 resetAll이 실행된다.
    beginHydration();

    void (async () => {
      useAppStore.getState().resetAll({ preserveWorkspaceArtifacts: true });
      await resetMameAll({ preserveWorkspaceArtifacts: true });

      // scratch(프로젝트 없음): 앱 데이터 디렉토리 스냅샷만 KURO에 복원한다.
      // 워크스페이스 레지스트리·MAME 복원·자동 탐지는 프로젝트 전용이라 건너뛴다.
      if (scratch) {
        const scratchResult = await readScratchAutosave(KURO_SCHEMA);
        if (!isCurrent()) return;
        if (scratchResult.status !== "read_failed") clearAutosaveBlock("kuro");
        await applyScratchKuroSnapshot(scratchResult, onMessage, isCurrent);
        return;
      }

      try {
        await openWorkspace(path);
      } catch (err) {
        console.warn("[autosave] workspace registry open failed", err);
      }
      if (!isCurrent()) return;

      const [kuroResult, mameResult] = await Promise.all([
        readAutosave(path, "kuro", KURO_SCHEMA),
        readAutosave(path, "mame", MAME_SCHEMA),
      ]);
      if (!isCurrent()) return;

      // 읽기에 성공한 kind만 봉인을 해제한다. read_failed면 아래에서 다시 건다.
      if (kuroResult.status !== "read_failed") clearAutosaveBlock("kuro");
      if (mameResult.status !== "read_failed") clearAutosaveBlock("mame");

      // ── kuro 결과 처리
      if (kuroResult.status === "ok") {
        try {
          await applyKuroSnapshot(kuroResult.snapshot);
          if (!isCurrent()) return;
          onMessage({
            kind: "kuro",
            variant: "restored",
            message: i18next.t("autosaveHydration.restored", { relative: formatRelativeTime(kuroResult.snapshot.saved_at) }),
            savedAt: kuroResult.snapshot.saved_at,
          });
        } catch (err) {
          console.warn("[autosave] kuro: apply snapshot failed", err);
        }
      } else if (kuroResult.status === "corrupted") {
        onMessage({
          kind: "kuro",
          variant: "corrupted",
          message: i18next.t("autosaveHydration.corrupted", { filename: kuroResult.backupPath.split("/").pop() ?? "kuro.json.bad-…" }),
        });
      } else if (kuroResult.status === "read_failed") {
        // 파일이 없는 것과 못 읽은 것은 다르다. 못 읽은 파일 위에 빈 상태를
        // 덮어쓰지 않도록 kuro 쓰기를 봉인하고 사용자에게 알린다.
        blockAutosaveWrites("kuro", kuroResult.error);
        onMessage({
          kind: "kuro",
          variant: "io_failed",
          message: readFailedMessage(kuroResult.filePath, kuroResult.error),
        });
      } else if (kuroResult.status === "schema_too_new") {
        onMessage({
          kind: "kuro",
          variant: "schema_too_new",
          message: i18next.t("autosaveHydration.schemaTooNew"),
        });
      } else if (kuroResult.status === "missing") {
        // 프로젝트 스냅샷이 없으면 scratch 스냅샷으로 이어서 작업하게 한다.
        const scratchResult = await readScratchAutosave(KURO_SCHEMA);
        if (!isCurrent()) return;
        if (scratchResult.status === "ok") {
          const applied = await applyScratchKuroSnapshot(
            scratchResult,
            onMessage,
            isCurrent,
            "promotion",
          );
          // 승격한 scratch 스냅샷은 여기서 소비된다. 지우지 않으면 이후 만드는
          // 신규 프로젝트마다 같은 FASTA·mutation·designResults가 다시 새어
          // 나가고, 다음 자동 저장이 그것을 프로젝트 파일에 영구화한다.
          if (applied) {
            try {
              await promoteScratchToProject(path);
            } catch (err) {
              const error = err instanceof Error ? err : new Error(String(err));
              console.warn("[autosave] kuro: scratch promotion failed", error);
              onMessage({
                kind: "kuro",
                variant: "io_failed",
                message: readFailedMessage(autosavePath(path, "kuro"), error),
              });
            }
          }
        } else if (scratchResult.status === "read_failed") {
          // scratch 파일을 못 읽었으면 사실만 알린다. 이후 쓰기 대상은 이 파일이
          // 아니라 프로젝트 파일이므로 kuro 쓰기를 봉인하지는 않는다.
          onMessage({
            kind: "kuro",
            variant: "io_failed",
            message: readFailedMessage(scratchResult.filePath, scratchResult.error),
          });
        }
      }
      if (!isCurrent()) return;

      // ── mame 결과 처리
      if (mameResult.status === "ok") {
        try {
          applyMameSnapshot(mameResult.snapshot as MameAutosaveSnapshot);
          if (!isCurrent()) return;
          onMessage({
            kind: "mame",
            variant: "restored",
            message: i18next.t("autosaveHydration.restored", { relative: formatRelativeTime(mameResult.snapshot.saved_at) }),
            savedAt: mameResult.snapshot.saved_at,
          });
        } catch (err) {
          console.warn("[autosave] mame: apply snapshot failed", err);
        }
      } else if (mameResult.status === "read_failed") {
        // kuro와 같은 이유로 mame 쓰기도 봉인한다. mame 자동 저장 역시 store
        // 구독 기반이라, 못 읽은 mame.json 위에 초기화된 상태가 덮어써진다.
        blockAutosaveWrites("mame", mameResult.error);
        onMessage({
          kind: "mame",
          variant: "io_failed",
          message: readFailedMessage(mameResult.filePath, mameResult.error),
        });
      } else if (mameResult.status === "corrupted") {
        onMessage({
          kind: "mame",
          variant: "corrupted",
          message: i18next.t("autosaveHydration.corrupted", { filename: mameResult.backupPath.split("/").pop() ?? "mame.json.bad-…" }),
        });
      } else if (mameResult.status === "schema_too_new") {
        onMessage({
          kind: "mame",
          variant: "schema_too_new",
          message: i18next.t("autosaveHydration.schemaTooNew"),
        });
      }
      if (!isCurrent()) return;
      // missing → 침묵

      // ── mame analyze-result 복원: 입력 스냅샷 복원 후, 결과 파일이 있으면
      //    사이드카 + store 재구성 후 2.2 review 뷰로 진입. RPC 실패가 입력
      //    스냅샷 "apply snapshot failed" 메시지를 오염시키지 않도록 별도 try/catch.
      try {
        const restored = await restoreMameResult(path);
        if (!isCurrent()) return;
        if (restored) {
          onMessage({
            kind: "mame",
            variant: "restored",
            message: i18next.t("autosaveHydration.workspaceRestored"),
          });
        }
      } catch (err) {
        console.warn("[autosave] mame: analyze-result restore failed", err);
      }
      if (!isCurrent()) return;

      // ── auto-detect: autosave 복원 후 여전히 비어있는 필드를 프로젝트 디렉토리에서 채운다
      await applyMameAutoDetect(path, (filled) => {
        if (!isCurrent()) return;
        if (filled.length > 0) {
          onMessage({
            kind: "mame",
            variant: "restored",
            message: i18next.t("autosaveHydration.autoDetected", { fields: filled.join(", ") }),
          });
        }
      });
    })().finally(() => {
      // 어느 경로로 끝나든(정상 종료, 조기 return, 예외) 게이트를 반드시 푼다.
      // 게이트가 남으면 이후 자동 저장이 통째로 죽는다.
      endHydration();
    });

    return () => {
      cancelled = true;
    };
  }, [project?.path, project?.scratch, onMessage]);
}
