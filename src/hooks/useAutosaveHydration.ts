/**
 * useAutosaveHydration.ts — Phase 4: 프로젝트 진입 시 자동 저장 파일 복원
 *
 * 프로젝트가 처음 활성화될 때 한 번만 실행된다.
 * kuro와 mame 두 스냅샷을 병렬로 읽고 각 store에 복원한다.
 * 결과물 필드(designResults, verdictRows, plateMap 등)는 복원하지 않는다.
 */

import { useEffect, useRef } from "react";
import i18next from "i18next";
import { useKumaProject } from "@/state/projectContext";
import { readAutosave } from "@/lib/autosave";
import { readMameResultSnapshot } from "@/lib/mame/resultSnapshot";
import { sendRequest as sendMameRequest } from "@/lib/ipc-mame";
import type { LoadAnalyzeResultResponse } from "@/types/mame/models";
import { KURO_SCHEMA } from "@/lib/kuroSnapshot";
import { MAME_SCHEMA } from "@/lib/mame/autosaveSnapshot";
import { detectProjectFiles, detectFromInputDir } from "@/lib/mame/detectProjectFiles";
import { openWorkspace } from "@/lib/workspace";
import { resolvePolymeraseName, retiredPolymeraseNotice } from "@/lib/polymeraseAliases";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { resetMameAll } from "@/store/mame/resetAll";
import type { AppState } from "@/store/appStore";
import type { AutosaveSnapshot } from "@/lib/autosave";
import type { MameAutosaveSnapshot } from "@/lib/mame/autosaveSnapshot";

// ─── 공개 타입 ────────────────────────────────────────────────────────────

export interface HydrationStatusMessage {
  kind: "kuro" | "mame";
  variant: "restored" | "corrupted" | "schema_too_new" | "missing";
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

function isEvolveproMode(value: unknown): value is AppState["evolveproMode"] {
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

async function applyKuroSnapshot(snapshot: AutosaveSnapshot): Promise<void> {
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
  if (isEvolveproMode(input?.evolvepro_mode)) {
    patch.evolveproMode = input.evolvepro_mode;
  } else if (typeof diversity?.pipeline_mode === "boolean") {
    patch.evolveproMode = diversity.pipeline_mode ? "pipeline" : "topN";
  }
  if (typeof input?.evolvepro_csv_path === "string" || input?.evolvepro_csv_path === null) {
    patch.evolveproCsvPath = input.evolvepro_csv_path ?? "";
  }
  if (typeof input?.others_source_path === "string" || input?.others_source_path === null) {
    patch.othersSourcePath = input.others_source_path ?? "";
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
  if (typeof input?.others_variant_column === "string" || input?.others_variant_column === null) {
    patch.othersVariantColumn = input.others_variant_column;
  }
  if (typeof input?.others_score_column === "string" || input?.others_score_column === null) {
    patch.othersScoreColumn = input.others_score_column;
  }
  if (isScoreOrder(input?.others_score_order)) {
    patch.othersScoreOrder = input.others_score_order;
  }
  if (typeof input?.others_sheet_name === "string" || input?.others_sheet_name === null) {
    patch.othersSheetName = input.others_sheet_name;
  }

  // parameters
  if (typeof params?.polymerase === "string") {
    // Retired profiles are remapped here rather than via setSelectedPolymerase,
    // so the snapshot GC range and overlap mode restored below are preserved.
    const { name, retiredFrom } = resolvePolymeraseName(params.polymerase);
    patch.selectedPolymerase = name;
    if (retiredFrom) {
      patch.statusMessage = retiredPolymeraseNotice(
        retiredFrom,
        name,
        typeof params?.gc_min === "number" ? params.gc_min : useAppStore.getState().gcMin,
        typeof params?.gc_max === "number" ? params.gc_max : useAppStore.getState().gcMax,
      );
    }
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

  useAppStore.setState(patch);

  const restoredMode = patch.evolveproMode ?? useAppStore.getState().evolveproMode;
  const activeSourcePath = restoredMode === "others"
    ? (typeof input?.others_source_path === "string" ? input.others_source_path : "")
    : (typeof input?.evolvepro_csv_path === "string" ? input.evolvepro_csv_path : "");
  if (activeSourcePath) {
    try {
      await useAppStore.getState().loadEvolveproCsv(activeSourcePath);
    } catch {
      console.warn("[autosave] kuro: EVOLVEpro source load failed, continuing restore");
    }
  }
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
 * - scratch 프로젝트는 reset까지만 수행하고 자동 저장 복원은 건너뛴다.
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

    void (async () => {
      useAppStore.getState().resetAll({ preserveWorkspaceArtifacts: true });
      await resetMameAll({ preserveWorkspaceArtifacts: true });
      if (scratch) return;
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
      } else if (kuroResult.status === "schema_too_new") {
        onMessage({
          kind: "kuro",
          variant: "schema_too_new",
          message: i18next.t("autosaveHydration.schemaTooNew"),
        });
      }
      if (!isCurrent()) return;
      // missing → 침묵

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
    })();

    return () => {
      cancelled = true;
    };
  }, [project?.path, project?.scratch, onMessage]);
}
