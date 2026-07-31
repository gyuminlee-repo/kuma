import { StrictMode } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import type { AutosaveSnapshot } from "@/lib/autosave";
import type { SdmPrimerResult } from "@/types/models";
import type { AnalyzeResult, ReplicateResult, RunHealthData, VerdictRecord, WellEntry } from "@/types/mame/models";
import type { Round } from "@/types/round";
import { BUILD_EVOLVEPRO_DEFAULT_STATE, createBuildEvolveproCompletion } from "@/lib/mame/buildEvolveproFormStorage";
import { applyKuroSnapshot, useAutosaveHydration, type AutosaveHydrationHandle } from "./useAutosaveHydration";

// ── Mocks ────────────────────────────────────────────────────────────────

const hooks = vi.hoisted(() => ({
  readAutosave: vi.fn(),
  readScratchAutosave: vi.fn(),
  deleteScratchAutosave: vi.fn(),
  blockAutosaveWrites: vi.fn(),
  clearAutosaveBlock: vi.fn(),
  beginHydration: vi.fn(),
  endHydration: vi.fn(),
  ensureAutosaveDir: vi.fn(),
  autosavePath: vi.fn(),
  atomicWriteJson: vi.fn(),
  readMameResultSnapshot: vi.fn(),
  sendMameRequest: vi.fn(),
  detectProjectFiles: vi.fn(),
  detectFromInputDir: vi.fn(),
  sendKuroRequest: vi.fn(),
  openWorkspace: vi.fn(),
  getLatestArtifact: vi.fn(),
  // 전역 fs stub 의 exists 는 항상 false 라, 그대로 두면 복원된 경로가 전부
  // "사라진 파일"로 판정돼 죽은 경로 정리에 지워진다. 이 테스트들이 검증하는
  // 것은 경로 존재가 아니라 복원·우선순위이므로 기본값을 present 로 둔다.
  // 사라진 경로 동작은 exists 를 false 로 뒤집는 전용 테스트에서 확인한다.
  exists: vi.fn(async (_path: string) => true),
}));

vi.mock("@tauri-apps/plugin-fs", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@tauri-apps/plugin-fs");
  return { ...actual, exists: hooks.exists };
});

// KURO 사이드카 RPC. applyKuroSnapshot이 loadEvolveproCsv를 통해 호출한다.
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: hooks.sendKuroRequest,
  setProgressHandler: vi.fn(),
}));

// 훅이 쓰는 autosave export를 전부 채운다. 하나라도 빠지면 vitest가
// "No <name> export is defined on the mock"으로 즉시 실패한다.
vi.mock("@/lib/autosave", () => ({
  readAutosave: hooks.readAutosave,
  readScratchAutosave: hooks.readScratchAutosave,
  deleteScratchAutosave: hooks.deleteScratchAutosave,
  blockAutosaveWrites: hooks.blockAutosaveWrites,
  clearAutosaveBlock: hooks.clearAutosaveBlock,
  beginHydration: hooks.beginHydration,
  endHydration: hooks.endHydration,
  ensureAutosaveDir: hooks.ensureAutosaveDir,
  autosavePath: hooks.autosavePath,
  atomicWriteJson: hooks.atomicWriteJson,
}));

vi.mock("@/lib/mame/resultSnapshot", () => ({
  readMameResultSnapshot: hooks.readMameResultSnapshot,
}));

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: hooks.sendMameRequest,
  isSidecarRunning: () => false,
}));

vi.mock("@/lib/mame/detectProjectFiles", () => ({
  detectProjectFiles: hooks.detectProjectFiles,
  detectFromInputDir: hooks.detectFromInputDir,
}));

vi.mock("@/lib/workspace", () => ({
  openWorkspace: hooks.openWorkspace,
  getLatestArtifact: hooks.getLatestArtifact,
  getActiveWorkspace: vi.fn(() => null),
  clearWorkspace: vi.fn(),
}));

// ── Fixtures ─────────────────────────────────────────────────────────────

const VERDICT: VerdictRecord = {
  native_barcode: "barcode1",
  custom_barcode: "1_1",
  file_size_kb: 120,
  read_count: 160,
  n_mixed_positions: 0,
  max_minor_allele_fraction: 0,
  n_low_depth_positions: 0,
  consensus_n_fraction: 0,
  n_low_quality_bases: 0,
  n_input_reads: 160,
  n_aligned_reads: 155,
  n_mapq_failed: 0,
  n_span_failed: 0,
  source_path: "/mock/NB01/1_1.fasta",
  aa_sequence: "MSTTS",
  observed_nt_changes: [],
  n_no_call_aa: 0,
  observed_aa_changes: ["V5F"],
  expected_mutations: ["V5F"],
  mutant_id: "V5F",
  verdict: "PASS",
  verdict_notes: "",
};

const REPLICATE: ReplicateResult = {
  mutant_id: "V5F",
  selected_plate: "barcode1",
  selection_reason: "only_pass",
  failed: false,
  plate_keys: ["barcode1"],
  // Critical: lossless per-plate verdict carried through AS-IS.
  plate_verdicts: { barcode1: VERDICT },
  is_fallback: false,
  fallback_reason: null,
};

const ANALYZE_RESULT: AnalyzeResult = {
  verdicts: [VERDICT],
  replicates: [REPLICATE],
  output_path: "/proj/out/mame_result.xlsx",
  summary: { total: 1, pass_count: 1, ambiguous_count: 0, fail_count: 0 },
  distribution_stats: {
    n_files: 1,
    file_size_kb: { min: 120, p05: 120, p25: 120, median: 120, p75: 120, p95: 120, max: 120, mean: 120, std: 0 },
    suggested_cutoff_kb: 50,
    suggested_method: "fixed_50",
    bimodal: false,
  },
};

const WELL: WellEntry = {
  well: "A01",
  barcode: "1_1",
  native_barcode: "barcode1",
  verdict: "PASS",
  mutant_id: "V5F",
  selected: true,
  notes: "",
  is_fallback: false,
  fallback_reason: null,
};

const RUN_HEALTH: RunHealthData = {
  per_plate_summary: {},
  file_size_distribution: {},
  suggested_cutoff_kb: 50,
  bimodal: false,
  suggested_method: "fixed_50",
  pore_yield_pct: null,
  throughput_timeline: null,
  barcode_distribution: null,
  cross_talk_candidates: [],
  recovered_mutants: null,
  total_mutants: 1,
  recovery_rate: 1,
};

const ROUND: Round = {
  id: "round_1",
  n: 1,
  created_at: "2026-07-30T00:00:00.000Z",
  status: "activity_linked",
  error_info: null,
  plate_meta: { plates: [{ plate_id: "plate01", wt_wells: ["A01"], control_wells: [] }] },
  design: {},
  genotype: {},
  activity: {
    records: [
      {
        plate_id: "plate01",
        well_id: "A01",
        value: 2.4,
        replicate_idx: 1,
        is_wt: false,
        source_file: "/proj/activity.csv",
      },
    ],
    plate_meta: { plates: [{ plate_id: "plate01", wt_wells: ["A01"], control_wells: [] }] },
  },
  merged_table: [
    {
      plate_id: "plate01",
      well_id: "A01",
      mutation: "V5F",
      mutation_source: "mame_genotype",
      expected_mutation: "V5F",
      called_mutation: "V5F",
      ngs_success: true,
      activity_raw_mean: 2.4,
      activity_raw_sd: 0,
      activity_replicates: [2.4],
      replicate_n: 1,
      fold_change: 2.3,
      log2_fc: 1.2,
    },
  ],
};

/** hydration 이 사용자에게 띄운 알림. 화면에 그리지 않으므로 여기서 모은다. */
const hydrationMessages: string[] = [];

function Harness() {
  useAutosaveHydration((m) => {
    hydrationMessages.push(m.message);
  });
  return null;
}

function renderHydration(): void {
  render(
    <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
      <Harness />
    </ProjectProvider>,
  );
}

describe("useAutosaveHydration: analyze-result restore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hydrationMessages.length = 0;
    useMameAppStore.getState().resetInput();
    useMameAppStore.getState().resetAnalysis();
    useMameAppStore.getState().setMameSubStep("setup.files");
    useRoundStore.setState({ rounds: [], active_round_id: null });

    // kuro: nothing to restore. mame input snapshot: nothing either.
    hooks.readAutosave.mockResolvedValue({ status: "missing" });
    hooks.readScratchAutosave.mockResolvedValue({ status: "missing" });
    // detection finds nothing (avoid touching the store further).
    hooks.detectProjectFiles.mockResolvedValue({});
    hooks.detectFromInputDir.mockResolvedValue({});
    // clearAllMocks 가 hoisted 기본 구현까지 지우므로 매 테스트마다 되세운다.
    // 기본은 present. 사라진 경로를 다루는 테스트가 개별적으로 뒤집는다.
    hooks.exists.mockResolvedValue(true);
    hooks.openWorkspace.mockResolvedValue(undefined);
    hooks.getLatestArtifact.mockResolvedValue(null);
    // sidecar RPCs: load_analyze_result ack, then get_plate_data empty grid.
    hooks.sendMameRequest.mockImplementation((method: string) => {
      if (method === "load_analyze_result") {
        return Promise.resolve({ restored: true, verdict_count: 1, replicate_count: 1 });
      }
      if (method === "get_plate_data") {
        return Promise.resolve({ wells: [] });
      }
      return Promise.resolve({});
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("replays the persisted result into the sidecar and lands on analyze.review", async () => {
    hooks.readMameResultSnapshot.mockResolvedValue({
      status: "ok",
      snapshot: {
        schema: 1,
        saved_at: new Date().toISOString(),
        kuma_version: "0.0.0-test",
        result: ANALYZE_RESULT,
      },
    });

    renderHydration();

    // load_analyze_result called with the persisted payload AS-IS.
    await waitFor(() => {
      expect(hooks.sendMameRequest).toHaveBeenCalledWith(
        "load_analyze_result",
        expect.objectContaining({ output_path: "/proj/out/mame_result.xlsx" }),
      );
    });

    const [, params] = hooks.sendMameRequest.mock.calls.find(
      (c) => c[0] === "load_analyze_result",
    ) as [string, { replicates: ReplicateResult[]; output_path: string }];
    // plate_verdicts carried through AS-IS (lossless plate-accent source).
    expect(params.replicates[0].plate_verdicts).toEqual({ barcode1: VERDICT });

    // get_plate_data called AFTER load_analyze_result (sidecar repopulated first).
    await waitFor(() => {
      expect(hooks.sendMameRequest).toHaveBeenCalledWith("get_plate_data", {});
    });

    // store repopulated + landed on the 2.2 review view.
    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
    const st = useMameAppStore.getState();
    expect(st.verdicts).toEqual([VERDICT]);
    expect(st.replicates).toEqual([REPLICATE]);
    expect(st.summary).toEqual(ANALYZE_RESULT.summary);
    expect(st.distributionStats).toEqual(ANALYZE_RESULT.distribution_stats);
  });

  it("skips restore silently when no result file exists", async () => {
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });

    renderHydration();

    // give the hydration IIFE time to settle (detect runs last).
    await waitFor(() => {
      expect(hooks.detectProjectFiles).toHaveBeenCalled();
    });

    expect(
      hooks.sendMameRequest.mock.calls.some((c) => c[0] === "load_analyze_result"),
    ).toBe(false);
    // Project entry resets the MAME phase, so the substep returns to the
    // default analyze.inputs (never silently advanced to analyze.review).
    expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.inputs");
    expect(useMameAppStore.getState().verdicts).toEqual([]);
  });

  it("clears a restored MAME path that no longer exists so auto-detect can refill it", async () => {
    // The snapshot carries absolute paths from the machine that wrote it. Here
    // the run folder is gone (project moved) but the reference still resolves.
    hooks.readAutosave.mockImplementation((_p: string, kind: string) => {
      if (kind === "mame") {
        return Promise.resolve({
          status: "ok",
          snapshot: {
            schema: 1,
            saved_at: new Date().toISOString(),
            kuma_version: "0.0.0-test",
            input: {
              input_dir: "/old-machine/run",
              expected_path: "",
              reference_path: "/proj/ref.fasta",
              output_path: "",
              sample_map_path: "",
            },
            parameters: {
              mode: "amplicon",
              ingest_mode: "barcode",
              input_mode: "raw_run",
              raw_run_params: undefined,
              cds_start: 0,
              cds_end: 0,
              min_file_size_kb: 50,
              many_cutoff: 5,
            },
          },
        });
      }
      return Promise.resolve({ status: "missing" });
    });
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });
    hooks.exists.mockImplementation(async (p: string) => p !== "/old-machine/run");
    // Auto-detect finds the run folder again inside the moved project.
    hooks.detectProjectFiles.mockResolvedValue({ inputDir: "/proj/20260731_1200_run" });

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().inputDir).toBe("/proj/20260731_1200_run");
    });
    // The path that still resolved is untouched, so a live value is never
    // discarded just because a sibling went missing.
    expect(useMameAppStore.getState().referencePath).toBe("/proj/ref.fasta");
  });

  it("names the inputs that stayed missing after auto-detect", async () => {
    hooks.readAutosave.mockImplementation((_p: string, kind: string) => {
      if (kind === "mame") {
        return Promise.resolve({
          status: "ok",
          snapshot: {
            schema: 1,
            saved_at: new Date().toISOString(),
            kuma_version: "0.0.0-test",
            input: {
              input_dir: "/old-machine/run",
              expected_path: "",
              reference_path: "",
              output_path: "",
              sample_map_path: "",
            },
            parameters: {
              mode: "amplicon",
              ingest_mode: "barcode",
              input_mode: "raw_run",
              raw_run_params: undefined,
              cds_start: 0,
              cds_end: 0,
              min_file_size_kb: 50,
              many_cutoff: 5,
            },
          },
        });
      }
      return Promise.resolve({ status: "missing" });
    });
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });
    hooks.exists.mockResolvedValue(false);
    // Nothing to re-detect: the raw run folder lived outside the project.
    hooks.detectProjectFiles.mockResolvedValue({});

    renderHydration();

    await waitFor(() => {
      expect(
        hydrationMessages.some((m) => /run folder|실행 폴더/i.test(m)),
      ).toBe(true);
    });
    expect(useMameAppStore.getState().inputDir).toBe("");
  });

  it("fills empty MAME expected mutations from the latest KURO SDM primer artifact", async () => {
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });
    hooks.getLatestArtifact.mockImplementation((type: string) => {
      if (type === "sdm_primer_xlsx") {
        return Promise.resolve({
          id: "artifact-1",
          app: "kuro",
          step: "sdm_primer",
          type: "sdm_primer_xlsx",
          path: "/proj/design/kuro_sdm_primers.xlsx",
          producedAt: "2026-07-31T00:00:00.000Z",
          mtime: "2026-07-31T00:00:00.000Z",
          sizeBytes: 128,
          stale: false,
        });
      }
      return Promise.resolve(null);
    });

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().expectedPath).toBe(
        "/proj/design/kuro_sdm_primers.xlsx",
      );
    });
    expect(hooks.getLatestArtifact).toHaveBeenCalledWith("sdm_primer_xlsx");
  });

  it("does not overwrite a restored MAME expected mutations path with a KURO artifact", async () => {
    hooks.readAutosave.mockImplementation((_path: string, kind: string) => {
      if (kind === "mame") {
        return Promise.resolve({
          status: "ok",
          snapshot: {
            schema: 2,
            saved_at: new Date().toISOString(),
            kuma_version: "0.0.0-test",
            rounds: [],
            active_round_id: null,
            input: {
              input_dir: "",
              expected_path: "/proj/manual_expected.xlsx",
              reference_path: "",
              output_path: "",
              sample_map_path: "",
            },
            parameters: {
              mode: "amplicon",
              ingest_mode: "barcode",
              input_mode: "raw_run",
              raw_run_params: undefined,
              cds_start: 0,
              cds_end: 0,
              min_file_size_kb: 50,
              many_cutoff: 5,
            },
          },
        });
      }
      return Promise.resolve({ status: "missing" });
    });
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });
    hooks.getLatestArtifact.mockResolvedValue({
      id: "artifact-1",
      app: "kuro",
      step: "sdm_primer",
      type: "sdm_primer_xlsx",
      path: "/proj/design/kuro_sdm_primers.xlsx",
      producedAt: "2026-07-31T00:00:00.000Z",
      mtime: "2026-07-31T00:00:00.000Z",
      sizeBytes: 128,
      stale: false,
    });

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().expectedPath).toBe(
        "/proj/manual_expected.xlsx",
      );
    });
  });

  it("restores result state carried inside the mame autosave snapshot", async () => {
    const buildCompletion = createBuildEvolveproCompletion(
      {
        ...BUILD_EVOLVEPRO_DEFAULT_STATE,
        layoutXlsx: "/proj/layout.xlsx",
        gcDataXlsx: "/proj/gc.xlsx",
        outputXlsx: "/proj/evolvepro.xlsx",
      },
      "/proj/evolvepro.xlsx",
    );
    hooks.readAutosave.mockImplementation((_path: string, kind: string) => {
      if (kind === "mame") {
        return Promise.resolve({
          status: "ok",
          snapshot: {
            schema: 2,
            saved_at: new Date().toISOString(),
            kuma_version: "0.0.0-test",
            rounds: [ROUND],
            active_round_id: "round_1",
            input: {
              input_dir: "/proj/run",
              expected_path: "/proj/expected.xlsx",
              reference_path: "/proj/ref.fa",
              output_path: "/proj/out",
              sample_map_path: "/proj/sample_map.xlsx",
            },
            parameters: {
              mode: "amplicon",
              ingest_mode: "barcode",
              input_mode: "raw_run",
              raw_run_params: {
                customBarcodesPath: "/proj/barcodes.xlsx",
                sequencingSummaryPath: "/proj/sequencing_summary.txt",
                minQscore: 10,
                lengthMin: 0,
                lengthMax: 0,
                targetLength: null,
                lengthToleranceBp: 50,
                normalizeHeaders: true,
                coverageFraction: 0.98,
                editDistRatio: 0.25,
                chimeraSplit: true,
              },
              cds_start: 1,
              cds_end: 900,
              min_file_size_kb: 50,
              many_cutoff: 5,
            },
            results: {
              verdicts: [VERDICT],
              replicates: [REPLICATE],
              summary: ANALYZE_RESULT.summary,
              distribution_stats: ANALYZE_RESULT.distribution_stats,
              wells: [WELL],
              selected_well: WELL,
              run_health: RUN_HEALTH,
              build_evolvepro_completion: buildCompletion,
              demux_result: null,
              amplicon_length_estimate: null,
              well_layout: { A01: "V5F" },
            },
          },
        });
      }
      return Promise.resolve({ status: "missing" });
    });
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
    const st = useMameAppStore.getState();
    expect(st.verdicts).toEqual([VERDICT]);
    expect(st.replicates).toEqual([REPLICATE]);
    expect(st.summary).toEqual(ANALYZE_RESULT.summary);
    expect(st.distributionStats).toEqual(ANALYZE_RESULT.distribution_stats);
    expect(st.wells).toEqual([WELL]);
    expect(st.selectedWell).toEqual(WELL);
    expect(st.runHealth).toEqual(RUN_HEALTH);
    expect(st.buildEvolveproCompletion).toEqual(buildCompletion);
    expect(st.wellLayout).toEqual({ A01: "V5F" });
    expect(useRoundStore.getState().rounds).toEqual([ROUND]);
    expect(useRoundStore.getState().active_round_id).toBe("round_1");
  });
});

// ── 복원된 결과물 vs 재선택된 variant 목록 ────────────────────────────────

/** designResults 항목 중 비교에 쓰이는 필드(mutation)만 실제 값으로 채운다. */
function designResultFor(mutation: string): SdmPrimerResult {
  return { mutation, aa_position: 1, codon_pos: 1 } as unknown as SdmPrimerResult;
}

function snapshotWithResults(mutation: string): AutosaveSnapshot {
  return {
    schema: 2,
    saved_at: new Date().toISOString(),
    kuma_version: "0.0.0-test",
    input: {
      sequence_path: null,
      selected_cds: null,
      mutation_text: mutation,
      mutation_input_mode: "evolvepro",
      evolvepro_mode: "pipeline",
      evolvepro_csv_path: "/proj/evolvepro.csv",
    },
    parameters: {},
    diversity: {},
    results: {
      designResults: [designResultFor(mutation)],
      successCount: 1,
      totalCount: 1,
      failedMutations: [{ mutation: "Z9Z", reason: "no candidate" }],
      plateMappings: [{ well: "A1", mutation, primer_name: "p", sequence: "ACGT", primer_type: "forward" }],
      dedupInfo: { [mutation]: ["A1"] },
      manuallySwapped: { [mutation]: "fwd" },
      customCandidates: { [mutation]: {} },
      rescuedMutationDetails: [{ mutation: "Z9Z" }],
    },
  } as unknown as AutosaveSnapshot;
}

/** loadEvolveproCsv가 돌려줄 재선택 결과. */
function mockReselection(variants: string[]): void {
  hooks.sendKuroRequest.mockImplementation((method: string) => {
    if (method === "load_evolvepro_csv") {
      return Promise.resolve({
        variants,
        y_preds: variants.map(() => 0.5),
        total_count: variants.length,
        selected_count: variants.length,
        pool_variants: variants,
        ranked_candidates: [],
        filtered_count: 0,
        domain_stats: null,
        pareto_replaced: 0,
        step_stats: null,
      });
    }
    return Promise.reject(new Error(`unexpected RPC: ${method}`));
  });
}

// ── hydrating 상태 / cancel ───────────────────────────────────────────────

describe("useAutosaveHydration: hydrating 상태와 cancel", () => {
  let handle: AutosaveHydrationHandle | null = null;

  /** 스냅샷이 들고 있는 mutation_text. 취소 가드가 뚫리면 이 값이 store에 착지한다. */
  const SNAPSHOT_MUTATION = "X9Y";
  /** 스냅샷이 가리키는 FASTA. loadSequence의 store 쓰기를 확인하는 데 쓴다. */
  const HELD_FASTA = "/proj/target.fa";

  function StatusHarness() {
    handle = useAutosaveHydration(() => {});
    return (
      <>
        <span data-testid="hydrating">{String(handle.hydrating)}</span>
        {/* phase는 null도 값이라 String()으로 찍어 "null"과 미렌더를 구분한다. */}
        <span data-testid="phase">{String(handle.phase)}</span>
      </>
    );
  }

  /** 매 호출이 새 element를 만든다. StatusHarness가 넘기는 onMessage 신원도 매 렌더 바뀐다. */
  function projectTree() {
    return (
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <StatusHarness />
      </ProjectProvider>
    );
  }

  /**
   * kuro 스냅샷 1건을 돌려주고 load_fasta 응답만 손으로 풀 수 있게 붙잡는다.
   *
   * 붙잡는 지점이 load_fasta인 이유: applyKuroSnapshot은 loadSequence await 직후
   * (useAutosaveHydration.ts 가드 (b))에서 스냅샷 patch 조립·적용을 끊는다. 그보다
   * 뒤인 load_evolvepro_csv를 붙잡으면 patch가 이미 setState된 뒤라(가드 (c) 통과)
   * mutationText 단언이 무엇을 검사하든 통과해 버린다.
   */
  function holdKuroSequenceLoad(): { release: (() => void) | null } {
    const gate: { release: (() => void) | null } = { release: null };
    hooks.readAutosave.mockImplementation((_path: string, kind: string) => {
      if (kind === "kuro") {
        return Promise.resolve({
          status: "ok",
          snapshot: {
            schema: 2,
            saved_at: new Date().toISOString(),
            kuma_version: "0.0.0-test",
            input: {
              sequence_path: HELD_FASTA,
              mutation_text: SNAPSHOT_MUTATION,
              mutation_input_mode: "evolvepro",
            },
            parameters: {},
            diversity: {},
          },
        });
      }
      return Promise.resolve({ status: "missing" });
    });
    hooks.sendKuroRequest.mockImplementation((method: string) => {
      if (method === "load_fasta") {
        return new Promise((resolve) => {
          gate.release = () => resolve({ header: "target", seq_length: 9, genes: [] });
        });
      }
      return Promise.resolve({});
    });
    return gate;
  }

  /** 붙잡아 둔 응답을 풀고, 뒤따르는 await 체인과 IIFE finally가 끝날 때까지 기다린다. */
  async function releaseAndSettle(gate: { release: (() => void) | null }): Promise<void> {
    await act(async () => {
      gate.release!();
      // 매크로태스크 경계까지 넘겨 남은 마이크로태스크를 전부 비운다.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    handle = null;
    useAppStore.getState().resetAll();
    useMameAppStore.getState().resetInput();
    useMameAppStore.getState().resetAnalysis();
    hooks.readAutosave.mockResolvedValue({ status: "missing" });
    hooks.readScratchAutosave.mockResolvedValue({ status: "missing" });
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });
    hooks.detectProjectFiles.mockResolvedValue({});
    hooks.detectFromInputDir.mockResolvedValue({});
    hooks.sendMameRequest.mockResolvedValue({});
    hooks.sendKuroRequest.mockResolvedValue({});
  });

  afterEach(() => {
    cleanup();
  });

  it("복원 중에는 hydrating이 true, 끝나면 false로 돌아온다", async () => {
    // auto-detect를 수동으로 풀 수 있게 잡아 둔다. 이 promise가 걸려 있는 동안
    // 복원 IIFE는 끝나지 않는다.
    let releaseDetect: (() => void) | null = null;
    hooks.detectProjectFiles.mockImplementation(
      () => new Promise((resolve) => { releaseDetect = () => resolve({}); }),
    );

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <StatusHarness />
      </ProjectProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("hydrating").textContent).toBe("true");
    });

    await waitFor(() => {
      expect(releaseDetect).not.toBeNull();
    });
    releaseDetect!();

    await waitFor(() => {
      expect(screen.getByTestId("hydrating").textContent).toBe("false");
    });
  });

  it("[진행 단계] 복원 중에는 단계가 노출되고 정상 종료 후 null로 돌아온다", async () => {
    // auto-detect에서 붙잡는다. applyMameAutoDetect의 첫 statement가
    // await detectProjectFiles이고 그 직전이 setRunPhase("detect")라, 이 promise가
    // 걸려 있는 동안 단계는 "detect"로 확정된다(단순 non-null보다 강한 고정).
    let releaseDetect: (() => void) | null = null;
    hooks.detectProjectFiles.mockImplementation(
      () => new Promise((resolve) => { releaseDetect = () => resolve({}); }),
    );

    render(projectTree());

    await waitFor(() => {
      expect(screen.getByTestId("phase").textContent).toBe("detect");
    });

    await waitFor(() => {
      expect(releaseDetect).not.toBeNull();
    });
    releaseDetect!();

    await waitFor(() => {
      expect(screen.getByTestId("hydrating").textContent).toBe("false");
    });
    // hydrating과 같은 지점에서 내려가야 한다. 단계가 남으면 다음 복원의 첫 프레임에
    // 옛 문구가 그대로 뜬다.
    expect(screen.getByTestId("phase").textContent).toBe("null");
  });

  it("[진행 단계] cancel이 단계를 즉시 비우고 뒤늦은 finally가 되살리지 않는다", async () => {
    const gate = holdKuroSequenceLoad();

    render(projectTree());

    await waitFor(() => {
      expect(gate.release).not.toBeNull();
    });
    // applyKuroSnapshot의 사이드카 왕복 구간은 "kuro" 단계다.
    expect(screen.getByTestId("phase").textContent).toBe("kuro");

    act(() => {
      handle!.cancel();
    });
    // 고아가 된 IIFE의 finally(사이드카 타임아웃까지 대기)를 기다리지 않는다.
    expect(screen.getByTestId("phase").textContent).toBe("null");

    // 그 finally가 뒤늦게 도착해도 activeRunRef 비교에서 져 옛 단계를 되살리지 못한다.
    await releaseAndSettle(gate);
    expect(screen.getByTestId("phase").textContent).toBe("null");
  });

  it("[취소 가드] 취소 후 도착한 loadSequence 응답이 스냅샷 patch를 store에 붓지 않는다", async () => {
    const gate = holdKuroSequenceLoad();

    render(projectTree());

    // applyKuroSnapshot이 loadSequence await에 걸릴 때까지 기다린다.
    await waitFor(() => {
      expect(gate.release).not.toBeNull();
    });

    act(() => {
      handle!.cancel();
    });
    await releaseAndSettle(gate);

    // 이미 떠난 loadSequence의 store 쓰기는 막지 못한다(cancel 계약 (2)의 명시된 한계).
    // 이 단언이 실패하면 취소 가드가 아니라 테스트가 해당 경로를 못 탄 것이다.
    expect(useAppStore.getState().fastaPath).toBe(HELD_FASTA);
    // 반대로 await 뒤 조립·적용되는 스냅샷 patch는 가드 (b)에서 끊긴다.
    expect(useAppStore.getState().mutationText).toBe("");
    expect(useAppStore.getState().mutationText).not.toBe(SNAPSHOT_MUTATION);
  });

  it("[R1] cancel이 자동 저장 게이트를 즉시 풀고 뒤늦은 finally가 두 번 풀지 않는다", async () => {
    const gate = holdKuroSequenceLoad();

    render(projectTree());

    await waitFor(() => {
      expect(gate.release).not.toBeNull();
    });
    expect(hooks.beginHydration).toHaveBeenCalledTimes(1);
    expect(hooks.endHydration).not.toHaveBeenCalled();

    act(() => {
      handle!.cancel();
    });
    // 고아가 된 IIFE의 finally(사이드카 타임아웃까지 대기)를 기다리지 않는다.
    expect(hooks.endHydration).toHaveBeenCalledTimes(1);

    await releaseAndSettle(gate);

    // fastaPath는 await 체인이 실제로 재개돼 finally까지 갔다는 증거다.
    expect(useAppStore.getState().fastaPath).toBe(HELD_FASTA);
    // gateReleased 래치가 이중 해제를 막아 begin 1회 : end 1회가 유지된다.
    expect(hooks.beginHydration).toHaveBeenCalledTimes(1);
    expect(hooks.endHydration).toHaveBeenCalledTimes(1);
  });

  it("[R4] cancel 후 같은 키로 effect가 재실행돼도 resetAll이 다시 돌지 않는다", async () => {
    const { rerender } = render(projectTree());

    await waitFor(() => {
      expect(hooks.readAutosave).toHaveBeenCalled();
    });
    const firstPassCalls = hooks.readAutosave.mock.calls.length;

    act(() => {
      handle!.cancel();
    });
    await waitFor(() => {
      expect(screen.getByTestId("hydrating").textContent).toBe("false");
    });

    // 취소 뒤 사용자가 입력한 값. resetAll이 다시 돌면 이 값이 날아간다.
    act(() => {
      useAppStore.setState({ mutationText: "user typed after cancel" });
    });

    // StatusHarness가 매 렌더 새 화살표를 onMessage로 넘기므로 리렌더만으로
    // effect deps가 바뀌어 재실행된다(언어 변경 시 t 의존 useCallback과 같은 경로).
    rerender(projectTree());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // cancel이 lastHydratedKey를 비우지 않으므로 dup-key 가드에서 skip된다.
    expect(useAppStore.getState().mutationText).toBe("user typed after cancel");
    expect(hooks.readAutosave.mock.calls.length).toBe(firstPassCalls);
  });

  it("[R4] cancel 후 언마운트했다가 재마운트하면 복원이 다시 실행된다", async () => {
    const first = render(projectTree());

    await waitFor(() => {
      expect(hooks.readAutosave).toHaveBeenCalled();
    });
    const firstPassCalls = hooks.readAutosave.mock.calls.length;

    act(() => {
      handle!.cancel();
    });
    await waitFor(() => {
      expect(screen.getByTestId("hydrating").textContent).toBe("false");
    });

    // 정상 재진입 경로(kuma:return-to-home → MainShell 언마운트 → 재진입).
    // 새 fiber는 lastHydratedKey ref 자체를 새로 만들므로 이 단언은 언마운트
    // cleanup의 키 비우기를 고정하지 못한다(그 몫은 아래 StrictMode 케이스).
    // 여기서 고정하는 것은 cancel이 재진입을 막지 않는다는 사용자 경로다.
    first.unmount();
    render(projectTree());

    await waitFor(() => {
      expect(hooks.readAutosave.mock.calls.length).toBeGreaterThan(firstPassCalls);
    });
  });

  it("[R4] StrictMode 모의 언마운트를 거쳐도 복원이 끝까지 완주한다", async () => {
    // 언마운트 cleanup이 lastHydratedKey를 비우지 않으면, 같은 fiber를 재사용하는
    // StrictMode의 두 번째 effect 실행이 dup-key 가드에 걸려 skip되고 첫 run은
    // cleanup에서 취소된다. 그 조합은 resetAll만 돌고 복원이 한 번도 적용되지
    // 않는 dev 빌드 전용 상태를 만든다.
    hooks.readAutosave.mockImplementation((_path: string, kind: string) => {
      if (kind === "kuro") {
        return Promise.resolve({
          status: "ok",
          snapshot: {
            schema: 2,
            saved_at: new Date().toISOString(),
            kuma_version: "0.0.0-test",
            input: {
              mutation_text: SNAPSHOT_MUTATION,
              mutation_input_mode: "evolvepro",
            },
            parameters: {},
            diversity: {},
          },
        });
      }
      return Promise.resolve({ status: "missing" });
    });

    render(<StrictMode>{projectTree()}</StrictMode>);

    await waitFor(() => {
      expect(useAppStore.getState().mutationText).toBe(SNAPSHOT_MUTATION);
    });
  });
});

describe("applyKuroSnapshot: 복원 결과물 vs 재선택 variant", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.getState().resetAll();
  });

  it("재선택 목록에 없는 mutation이 있으면 결과물과 파생 상태를 전부 비운다", async () => {
    mockReselection(["A1B"]);

    const outcome = await applyKuroSnapshot(snapshotWithResults("X9Y"));

    expect(outcome.resultsDiscarded).toBe(true);
    const st = useAppStore.getState();
    expect(st.mutationText).toBe("A1B");
    expect(st.designResults).toEqual([]);
    expect(st.successCount).toBe(0);
    expect(st.totalCount).toBe(0);
    expect(st.failedMutations).toEqual([]);
    expect(st.plateMappings).toEqual([]);
    expect(st.dedupInfo).toEqual({});
    expect(st.manuallySwapped).toEqual({});
    expect(st.customCandidates).toEqual({});
    expect(st.rescuedMutationDetails).toEqual([]);
  });

  it("재선택 목록이 결과물을 전부 포함하면 결과물을 유지한다", async () => {
    mockReselection(["X9Y"]);

    const outcome = await applyKuroSnapshot(snapshotWithResults("X9Y"));

    expect(outcome.resultsDiscarded).toBe(false);
    const st = useAppStore.getState();
    expect(st.designResults).toHaveLength(1);
    expect(st.successCount).toBe(1);
    expect(st.plateMappings).toHaveLength(1);
  });
});

describe("applyKuroSnapshot: 프로젝트 폴더 이식", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.getState().resetAll();
  });

  /** evolvepro_csv_path 만 바꾼 스냅샷. 결과물은 재선택과 일치시켜 폐기를 피한다. */
  function snapshotWithCsvPath(csvPath: string): AutosaveSnapshot {
    const snapshot = snapshotWithResults("X9Y") as unknown as {
      input: Record<string, unknown>;
    };
    return {
      ...(snapshot as unknown as AutosaveSnapshot),
      input: { ...snapshot.input, evolvepro_csv_path: csvPath },
    } as unknown as AutosaveSnapshot;
  }

  it("project:// 경로를 현재 프로젝트 폴더 기준으로 되살려 로드한다", async () => {
    mockReselection(["X9Y"]);

    await applyKuroSnapshot(
      snapshotWithCsvPath("project://evolvepro.csv"),
      undefined,
      "/newpc/run7",
    );

    // 다른 PC의 폴더 기준으로 다시 조립된 경로로 사이드카를 호출해야 한다.
    expect(useAppStore.getState().evolveproCsvPath).toBe("/newpc/run7/evolvepro.csv");
    expect(hooks.sendKuroRequest).toHaveBeenCalledWith(
      "load_evolvepro_csv",
      expect.objectContaining({ filepath: "/newpc/run7/evolvepro.csv" }),
    );
  });

  it("구 스냅샷의 절대 경로는 기준 폴더와 무관하게 그대로 쓴다", async () => {
    mockReselection(["X9Y"]);

    await applyKuroSnapshot(
      snapshotWithCsvPath("/oldpc/run7/evolvepro.csv"),
      undefined,
      "/newpc/run7",
    );

    expect(useAppStore.getState().evolveproCsvPath).toBe("/oldpc/run7/evolvepro.csv");
  });

  it("입력을 열지 못하면 복원은 이어가되 열지 못한 경로를 보고한다", async () => {
    hooks.sendKuroRequest.mockRejectedValue(new Error("ENOENT"));

    const outcome = await applyKuroSnapshot(
      snapshotWithCsvPath("/oldpc/run7/evolvepro.csv"),
      undefined,
      "/newpc/run7",
    );

    // 조용히 넘어가면 결과물만 남고 근거 입력이 빠진 상태를 정상으로 오인한다.
    expect(outcome.unavailableInputs).toEqual(["/oldpc/run7/evolvepro.csv"]);
    expect(useAppStore.getState().designResults).toHaveLength(1);
  });

  it("정상 복원이면 열지 못한 입력 목록이 비어 있다", async () => {
    mockReselection(["X9Y"]);

    const outcome = await applyKuroSnapshot(
      snapshotWithCsvPath("project://evolvepro.csv"),
      undefined,
      "/newpc/run7",
    );

    expect(outcome.unavailableInputs).toEqual([]);
  });
});
