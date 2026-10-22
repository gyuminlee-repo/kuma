/**
 * analysisSlice.loadSampleData.test.ts
 *
 * MAME loadSampleData() 동작 검증:
 * - 기존 15개 경로 순서를 유지하며 재시퀀싱 리소스 경로 추가
 * - activity.set_plate_meta + activity.upload RPC 호출 파라미터
 * - 입력 경로 setter + hardcoded sample 결과 populate
 * - activity RPC 실패 시 fallback (결과는 populate, 메시지 변경)
 * - resolveResource 실패 시 abort (결과 미populate, error 메시지)
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const mockSendRequest = vi.fn();

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => mockSendRequest(...args),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@tauri-apps/api/path", () => ({
  resolveResource: vi.fn((p: string) => Promise.resolve(`/resolved/${p}`)),
}));

// readTextFile: return empty JSON object by default (fixture load warn-only on parse failure)
// exists: default to true so `resolveResource` success continues to mean "the
// file is there" for tests that only care about the RPC/populate behaviour.
vi.mock("@tauri-apps/plugin-fs", () => ({
  readTextFile: vi.fn(() => Promise.resolve("{}")),
  exists: vi.fn(() => Promise.resolve(true)),
  copyFile: vi.fn(() => Promise.resolve()),
  mkdir: vi.fn(() => Promise.resolve()),
}));

// seedBuildEvolveproForm touches localStorage; mock to avoid jsdom side-effects in unit tests
vi.mock("@/lib/mame/buildEvolveproFormStorage", () => ({
  seedBuildEvolveproForm: vi.fn(),
  loadBuildEvolveproFromStorage: vi.fn(() => ({ verdictXlsx: "" })),
  saveBuildEvolveproToStorage: vi.fn(),
}));

import { resolveResource } from "@tauri-apps/api/path";
import { copyFile, exists, readTextFile } from "@tauri-apps/plugin-fs";
import {
  loadBuildEvolveproFromStorage,
  saveBuildEvolveproToStorage,
  seedBuildEvolveproForm,
} from "@/lib/mame/buildEvolveproFormStorage";
import {
  sampleReplicates,
  sampleSummary,
  sampleVerdicts,
  sampleWells,
} from "@/lib/mame/sampleData";
import { useRoundStore } from "@/store/round/roundSlice";
import type { AppState } from "../types";
import { createAnalysisSlice } from "./analysisSlice";
import { resequenceStore } from "../mameAppStore";
import { sendRunRequest } from "@/lib/mame/runRequests";
import fixture from "../../../../src-tauri/samples/mame/sample_analysis_result.json";
import originalResponse from "../../../../src-tauri/samples/mame/sample_analyze_response.json";
import repeatedResponse from "../../../../src-tauri/samples/mame/sample_resequence_response.json";

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = {
    referencePath: "",
    expectedPath: "",
    rawRunParams: {
      customBarcodesPath: "",
      sequencingSummaryPath: "",
    } as AppState["rawRunParams"],
    validationErrors: [],
    analyzeMessage: "",
    setReferencePath: vi.fn((p: string) => {
      state.referencePath = p;
    }),
    chooseExpectedPath: vi.fn((p: string) => {
      state.expectedPath = p;
    }),
    setParams: vi.fn((params: { rawRunParams?: Partial<AppState["rawRunParams"]> }) => {
      if (params.rawRunParams) {
        state.rawRunParams = {
          ...(state.rawRunParams as AppState["rawRunParams"]),
          ...params.rawRunParams,
        };
      }
    }),
    ...initial,
  };

  const set = (
    updater:
      | Partial<AppState>
      | ((current: AppState) => Partial<AppState>),
  ) => {
    const updates =
      typeof updater === "function" ? updater(state as AppState) : updater;
    Object.assign(state, updates);
  };
  const get = () => state as AppState;
  const slice = createAnalysisSlice(
    set as Parameters<typeof createAnalysisSlice>[0],
    get as Parameters<typeof createAnalysisSlice>[1],
    {} as Parameters<typeof createAnalysisSlice>[2],
  );
  Object.assign(state, slice, initial);
  return state as AppState;
}

describe("mame analysisSlice.loadSampleData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (resolveResource as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      (p: string) => Promise.resolve(`/resolved/${p}`),
    );
    // Reset singleton roundStore between tests so addRound id assertions are stable.
    useRoundStore.setState({ rounds: [], active_round_id: null });
    resequenceStore.getState().clearResults();
    vi.mocked(readTextFile).mockResolvedValue("{}");
    vi.mocked(exists).mockResolvedValue(true);
  });

  it("resolves bundled resources, creates one round with WT metadata, and populates inputs and results", async () => {
    // activity.upload returns records + plate_meta; hydrated into round.activity
    mockSendRequest.mockImplementation((method: string) => {
      if (method === "activity.upload") {
        return Promise.resolve({
          records: [
            { plate_id: "plate01", well_id: "A1", value: 1.011, replicate_idx: 1, is_wt: true },
          ],
          plate_meta: {
            plates: [
              { plate_id: "plate01", wt_wells: ["H12"], control_wells: [] },
            ],
          },
        });
      }
      return Promise.resolve({});
    });
    // `seedBuildEvolveproForm`'s second arg is `formStoragePath`, not
    // `projectPath`: the latter stays null for a scratch session (it gates
    // the result-snapshot write), so step 4 keys its localStorage row on the
    // always-populated mirror instead. Both are set here since this test's
    // project is not scratch.
    const store = makeStore({ projectPath: "/project", formStoragePath: "/project" });

    await store.loadSampleData();

    const expectedPaths = [
      "samples/mame/reference.fasta",
      "samples/mame/03_mame_expected_mutations.xlsx",
      "samples/mame/04_mame_custom_barcodes.xlsx",
      "samples/mame/06_mame_plate_layout.xlsx",
      "samples/mame/07_mame_activity_long.csv",
      "samples/mame/02_mame_barcode_seeds.xlsx",
      "samples/mame/egfp_with_flanks.fa",
      "samples/mame/09_mame_agilent_rep_batch.xlsx",
      "samples/mame/10_mame_gc_prenormalised.xlsx",
      "samples/mame/11_mame_gc_fid_round1_raw.xlsx",
      "samples/mame/sample_analysis_result.json",
      "samples/mame/13_mame_verdict.xlsx",
      "samples/mame/14_mame_activity_long_raw.csv",
      "samples/mame/12_mame_agilent_numeric_index.xlsx",
      "samples/mame/16_mame_agilent_numeric_confirmation.xlsx",
      "samples/mame/sample_analyze_response.json",
      "samples/mame/sample_resequence_response.json",
      "samples/mame/18_mame_resequence_verdict.xlsx",
      "samples/mame/sample_original_picks.csv",
      "samples/mame/18_mame_resequence_verdict_picks.csv",
      "samples/mame/19_mame_activity_resequence_clone.csv",
    ];
    // One per entry of `expectedPaths` and nothing else. The sample map
    // (`05_mame_sample_map.xlsx`) was dropped along with the field it filled;
    // the verdict workbook and the raw long file were added because step 4
    // cannot finish a build without the first and opens on the scale of the
    // second. The numeric-index and numeric-confirmation files were added so
    // clicking Load Sample Data seeds every file that has a step 4 field to
    // hold it (07_...xlsx, 08_..., 15_... still have none).
    expect(resolveResource).toHaveBeenCalledTimes(expectedPaths.length);
    for (const p of expectedPaths) {
      expect(resolveResource).toHaveBeenCalledWith(p);
    }

    // 2. Round created in roundStore with sample WT-well plate meta
    const roundState = useRoundStore.getState();
    expect(roundState.rounds.length).toBe(1);
    const round = roundState.rounds[0]!;
    expect(round.plate_meta.plates).toEqual([
      { plate_id: "plate01", wt_wells: ["H12"], control_wells: [] },
    ]);
    expect(roundState.active_round_id).toBe(round.id);

    // 3. activity.set_plate_meta RPC uses the freshly created round id + WT wells
    expect(mockSendRequest).toHaveBeenCalledWith(
      "activity.set_plate_meta",
      expect.objectContaining({
        round_id: round.id,
        plate_meta: expect.objectContaining({
          plates: [
            { plate_id: "plate01", wt_wells: ["H12"], control_wells: [] },
          ],
        }),
      }),
    );

    // 4. activity.upload RPC
    expect(mockSendRequest).toHaveBeenCalledWith(
      "activity.upload",
      expect.objectContaining({
        round_id: round.id,
        file_path: "/resolved/samples/mame/07_mame_activity_long.csv",
        format: "csv",
      }),
    );

    // 5. round.activity hydrated from upload response
    expect(round.activity).not.toBeNull();
    expect(round.activity?.plate_meta.plates[0]?.wt_wells).toEqual(["H12"]);
    expect(round.activity?.records.length).toBeGreaterThan(0);

    // 4. 입력 경로 store populated. The analyze reference is the flanked
    // construct, not the bare CDS: the demo's barcode workbook was designed
    // against `egfp_with_flanks.fa`, so only that file contains the primer
    // tails `resolve_amplicon_reference` looks for. Pointing this at
    // `reference.fasta` puts the demo back on the NOT_FOUND path.
    expect(store.referencePath).toBe("/resolved/samples/mame/egfp_with_flanks.fa");
    expect(store.expectedPath).toBe(
      "/resolved/samples/mame/03_mame_expected_mutations.xlsx",
    );
    expect(store.rawRunParams.customBarcodesPath).toBe(
      "/resolved/samples/mame/04_mame_custom_barcodes.xlsx",
    );

    // 5. hardcoded sample 결과 populated
    expect(store.verdicts).toEqual(sampleVerdicts());
    expect(store.replicates).toEqual(sampleReplicates());
    expect(store.summary).toEqual(sampleSummary());
    expect(store.wells).toEqual(sampleWells());
    expect(store.selectedWell).not.toBeNull();

    // The measurement source is the raw file, not the relative twin: the form
    // opens on the raw scale, and seeding the relative one would divide values
    // by a wild-type mean they already carry. The verdict workbook is seeded
    // because step 4 requires it and sample data has no other source for it.
    expect(seedBuildEvolveproForm).toHaveBeenCalledWith(
      {
        activityPath: "/resolved/samples/mame/14_mame_activity_long_raw.csv",
        layoutXlsx: "/resolved/samples/mame/06_mame_plate_layout.xlsx",
        gcDataXlsx: "/resolved/samples/mame/10_mame_gc_prenormalised.xlsx",
        round1ReportXlsx:
          "/resolved/samples/mame/11_mame_gc_fid_round1_raw.xlsx",
        remeasureReportXlsx:
          "/resolved/samples/mame/09_mame_agilent_rep_batch.xlsx",
        numericReportXlsx:
          "/resolved/samples/mame/12_mame_agilent_numeric_index.xlsx",
        remeasureNumericXlsx:
          "/resolved/samples/mame/16_mame_agilent_numeric_confirmation.xlsx",
        verdictXlsx: "/project/sample_data/mame/original/13_mame_verdict.xlsx",
        expectedXlsx: "/resolved/samples/mame/03_mame_expected_mutations.xlsx",
      },
      "/project",
    );

    // 6. 성공 메시지
    expect(store.analyzeMessage).toMatch(/loaded/i);
    expect(store.analyzeMessage).not.toMatch(/activity RPC unavailable/);
  });

  it("shows the bundled run rather than the fallback when the fixture carries one", async () => {
    // The point of the fixture is that the results screen states the same
    // campaign the rest of the sample files describe. A fixture that is read
    // for run health alone leaves the screen showing a different plate than
    // step 4 is about to build from, which is how the two drifted apart.
    const fixtureVerdicts = [
      { native_barcode: "1_1", custom_barcode: "1_1", verdict: "PASS", mutant_id: "Y67H" },
    ];
    const fixtureWells = [
      { well: "A1", mutant_id: "Y67H", verdict: "PASS", selected: true },
    ];
    (readTextFile as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      JSON.stringify({
        verdicts: fixtureVerdicts,
        replicates: [{ mutant_id: "Y67H", selected_plate: "NB01", failed: false }],
        summary: { total: 1, pass_count: 1, ambiguous_count: 0, fail_count: 0 },
        wells: fixtureWells,
        runHealth: { cross_talk_status: "not_run" },
      }),
    );
    const store = makeStore();

    await store.loadSampleData();

    expect(store.verdicts).toEqual(fixtureVerdicts);
    expect(store.wells).toEqual(fixtureWells);
    expect(store.summary?.total).toBe(1);
    expect(store.verdicts).not.toEqual(sampleVerdicts());
    // The count in the message is read off what loaded, so it moves with it.
    expect(store.analyzeMessage).toMatch(/1 wells/);
  });

  it("drops the replicate axis of the previous run", async () => {
    // The fixture verdicts carry `barcode1`, `barcode2`, ... as their
    // native_barcode, so a `sort_barcodeNN` selection left over from a real run
    // marks every sample well missing_replicate and has ReplicateModeNotice
    // compare that run's barcode count against this fixture. null is "no axis
    // stated", which is what a consensus-dir fixture can say; `[]` would claim
    // the fixture was pooled.
    const store = makeStore({
      selectedNativeBarcodes: ["sort_barcode06", "sort_barcode20"],
      detectedBarcodeCount: 3,
    });

    await store.loadSampleData();

    expect(store.selectedNativeBarcodes).toBeNull();
    expect(store.detectedBarcodeCount).toBeNull();
  });

  it("falls back to mock results when activity RPC throws", async () => {
    mockSendRequest.mockRejectedValueOnce(new Error("sidecar down"));
    const store = makeStore();

    await store.loadSampleData();

    // 입력 경로 여전히 설정됨
    expect(store.referencePath).toBe("/resolved/samples/mame/egfp_with_flanks.fa");
    expect(store.rawRunParams.customBarcodesPath).toBe(
      "/resolved/samples/mame/04_mame_custom_barcodes.xlsx",
    );

    // hardcoded 결과 여전히 populated
    expect(store.verdicts).toEqual(sampleVerdicts());
    expect(store.replicates).toEqual(sampleReplicates());
    expect(store.summary).toEqual(sampleSummary());
    expect(store.wells.length).toBeGreaterThan(0);

    // 메시지에 fallback 언급
    expect(store.analyzeMessage).toMatch(/activity RPC unavailable/);
    expect(store.analyzeMessage).toMatch(/sidecar down/);
  });

  it("aborts and reports Sample load failed when resolveResource throws", async () => {
    (resolveResource as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("resource missing"),
    );
    const store = makeStore();

    await store.loadSampleData();

    // 결과 미populate (초기 상태 유지)
    expect(store.verdicts).toEqual([]);
    expect(store.replicates).toEqual([]);
    expect(store.summary).toBeNull();
    expect(store.wells).toEqual([]);
    expect(store.selectedWell).toBeNull();

    // 활동 RPC 미호출
    expect(mockSendRequest).not.toHaveBeenCalled();

    // 에러 메시지
    expect(store.analyzeMessage).toMatch(/Sample load failed/);
    expect(store.analyzeMessage).toMatch(/resource missing/);
  });

  // Regression for defect 1: `resolveResource` only concatenates a path and
  // never touches disk, so a resolved-but-absent file used to be read as a
  // successful load. These pin the behaviour once `exists()` is consulted:
  // a missing critical file aborts the same way a rejected resolve does, and
  // a missing optional file is named to the user instead of being seeded as
  // a path that will fail much later inside the sidecar.
  describe("resolveResource succeeds but exists() reports the file is gone (defect 1)", () => {
    it("aborts with Sample load failed when the critical reference.fasta does not exist on disk", async () => {
      (exists as unknown as ReturnType<typeof vi.fn>).mockImplementation((p: string) =>
        Promise.resolve(!p.includes("reference.fasta")),
      );
      const store = makeStore();

      await store.loadSampleData();

      expect(store.verdicts).toEqual([]);
      expect(store.wells).toEqual([]);
      expect(mockSendRequest).not.toHaveBeenCalled();
      expect(store.analyzeMessage).toMatch(/Sample load failed/);
      expect(store.analyzeMessage).toMatch(/reference\.fasta/);
      expect(store.sampleDataLoaded).toBe(false);
    });

    it("names a missing optional file instead of seeding its (non-existent) path into step 4", async () => {
      (exists as unknown as ReturnType<typeof vi.fn>).mockImplementation((p: string) =>
        Promise.resolve(!p.includes("13_mame_verdict.xlsx")),
      );
      const store = makeStore({ projectPath: "/project", formStoragePath: "/project" });

      await store.loadSampleData();

      // The rest of the load still succeeds: this is a non-critical file.
      expect(store.verdicts).toEqual(sampleVerdicts());
      expect(store.sampleDataLoaded).toBe(true);

      // The user is told the file is missing...
      expect(store.analyzeMessage).toMatch(/missing optional files/);
      expect(store.analyzeMessage).toMatch(/13_mame_verdict\.xlsx/);

      // ...and the absent path is not seeded into the step 4 form (seeding a
      // path that does not exist reproduces the original defect one step
      // later: a Build that fails with "verdict_xlsx not found" instead of
      // being told up front that the sample never had one).
      const [seededPaths] = (seedBuildEvolveproForm as unknown as ReturnType<typeof vi.fn>)
        .mock.calls[0] as [Record<string, string | undefined>, string];
      expect(seededPaths.verdictXlsx).toBeUndefined();
    });
  });

  // Regression: 12_mame_agilent_numeric_index.xlsx and
  // 16_mame_agilent_numeric_confirmation.xlsx were bundled and declared in
  // tauri.conf.json resources but never referenced by loadSampleData, so
  // clicking Load Sample Data left numericReportXlsx/remeasureNumericXlsx
  // empty even though BuildEvolveproFormState has dedicated fields for them.
  it("seeds numericReportXlsx and remeasureNumericXlsx from #12 and #16", async () => {
    const store = makeStore({ projectPath: "/project", formStoragePath: "/project" });

    await store.loadSampleData();

    const [seededPaths] = (seedBuildEvolveproForm as unknown as ReturnType<typeof vi.fn>)
      .mock.calls[0] as [Record<string, string | undefined>, string];
    expect(seededPaths.numericReportXlsx).toBe(
      "/resolved/samples/mame/12_mame_agilent_numeric_index.xlsx",
    );
    expect(seededPaths.remeasureNumericXlsx).toBe(
      "/resolved/samples/mame/16_mame_agilent_numeric_confirmation.xlsx",
    );
  });

  function useBundledResponses() {
    vi.mocked(readTextFile).mockImplementation(async (path) => {
      if (String(path).endsWith("sample_analyze_response.json")) return JSON.stringify(originalResponse);
      if (String(path).endsWith("sample_resequence_response.json")) return JSON.stringify(repeatedResponse);
      return JSON.stringify(fixture);
    });
  }

  it("preserves the original screen while populating two independent replayable run snapshots", async () => {
    // Given the bundled campaign and its full RPC responses.
    useBundledResponses();
    const store = makeStore({ runScope: "primary", formStoragePath: "/sample" });
    const phase = resequenceStore.getState().mamePhase;

    // When the single primary command loads the campaign.
    await store.loadSampleData();

    // Then the original projection stays unchanged and both cache snapshots exist.
    const repeated = resequenceStore.getState();
    expect(store.verdicts).toEqual(fixture.verdicts);
    expect(store.replicates).toEqual(fixture.replicates);
    expect(store.summary).toEqual(fixture.summary);
    expect(store.wells).toEqual(fixture.wells);
    expect(store.runHealth).toEqual(fixture.runHealth);
    expect(store.analyzeResult?.verdicts).toEqual(originalResponse.verdicts);
    const original = "/sample/sample_data/mame/original";
    const copies = "/sample/sample_data/mame/resequence";
    expect(store.analyzeResult?.output_path).toBe(`${original}/13_mame_verdict.xlsx`);
    expect(repeated.analyzeResult?.output_path).toBe(`${copies}/18_mame_resequence_verdict.xlsx`);
    expect(store.analyzeResult?.janus_autosave?.output_path).toBe(`${original}/sample_original_picks.csv`);
    expect(repeated.analyzeResult?.janus_autosave?.output_path).toBe(`${copies}/18_mame_resequence_verdict_picks.csv`);
    expect(store.janusAutosave?.output_path).toBe(`${original}/sample_original_picks.csv`);
    // The sidecar refuses two independent runs whose outputs share a parent
    // directory, so the two copies must sit in different folders.
    const parent = (path: string | undefined) => path?.replace(/[/\\][^/\\]*$/, "");
    expect(parent(store.analyzeResult?.output_path)).not.toBe(parent(repeated.analyzeResult?.output_path));
    // Writable outputs are copies inside the project, never the resource dir.
    for (const run of [store.analyzeResult, repeated.analyzeResult]) {
      expect(run?.output_path.startsWith("/sample/")).toBe(true);
      expect(run?.output_path).not.toContain("/resolved/");
    }
    expect(copyFile).toHaveBeenCalledWith("/resolved/samples/mame/18_mame_resequence_verdict.xlsx", `${copies}/18_mame_resequence_verdict.xlsx`);
    // 2.3 inputs are seeded like the primary sample, outputs go to the copy folder.
    expect(repeated.referencePath).toBe("/resolved/samples/mame/egfp_with_flanks.fa");
    expect(repeated.expectedPath).toBe("/resolved/samples/mame/03_mame_expected_mutations.xlsx");
    expect(repeated.rawRunParams.customBarcodesPath).toBe("/resolved/samples/mame/04_mame_custom_barcodes.xlsx");
    expect(repeated.outputPath).toBe(copies);
    expect(repeated.analyzeMessage).toMatch(/Sample data loaded \(51 wells/);
    expect(repeated.verdicts).toEqual(repeatedResponse.verdicts);
    expect(repeated.replicates).toEqual(repeatedResponse.replicates);
    expect(repeated.summary).toEqual(repeatedResponse.summary);
    expect(repeated.wells).toEqual(repeatedResponse.wells);
    expect(repeated.runHealth).toEqual(repeatedResponse.runHealth);
    expect(repeated.compareParams).toEqual(repeatedResponse.compare_params);
    expect(repeated.sampleDataLoaded).toBe(true);
    expect(repeated.mamePhase).toBe(phase);
    expect(useRoundStore.getState().rounds).toHaveLength(1);
    expect(seedBuildEvolveproForm).toHaveBeenCalledTimes(1);
    expect(vi.mocked(seedBuildEvolveproForm).mock.calls[0]?.[0]).not.toHaveProperty("resequenceEvidence");
    expect(mockSendRequest.mock.calls.map(([method]) => method)).not.toContain("analyze");
  });

  it("attaches the rebound response to resequencing cache consumers after loading samples", async () => {
    // Given a loaded independent run.
    useBundledResponses();
    await makeStore({ formStoragePath: "/sample" }).loadSampleData();
    mockSendRequest.mockClear();

    // When a cache consumer asks for that run's current selection.
    await sendRunRequest(resequenceStore.getState(), "get_plate_data", {});

    // Then a restarted sidecar receives the complete independent snapshot.
    expect(mockSendRequest).toHaveBeenCalledWith("get_plate_data", {
      run_scope: "resequence",
      result_snapshot: resequenceStore.getState().analyzeResult,
    });
  });

  it.each([
    "sample_resequence_response.json",
    "18_mame_resequence_verdict.xlsx",
  ])("clears stale repeat evidence while retaining the original when %s is absent", async (missing) => {
    // Given an old repeat and an optional resource missing on reload.
    useBundledResponses();
    const store = makeStore({ formStoragePath: "/sample" });
    await store.loadSampleData();
    vi.mocked(exists).mockImplementation(async (path) => !String(path).endsWith(missing));

    // When the primary command loads the partial bundle.
    await store.loadSampleData();

    // Then there is no stale repeat to link and the missing resource is named.
    expect(store.analyzeResult?.output_path).toBe("/sample/sample_data/mame/original/13_mame_verdict.xlsx");
    expect(store.sampleDataLoaded).toBe(true);
    expect(resequenceStore.getState().analyzeResult).toBeNull();
    expect(resequenceStore.getState().wells).toEqual([]);
    expect(store.analyzeMessage).toContain(missing);
  });

  it.each([
    "/resolved/samples/mame/13_mame_verdict.xlsx",
    "/sample/sample_data/mame/13_mame_verdict.xlsx",
  ])("replaces a verdict workbook an earlier sample load left at %s", async (previous) => {
    // Given a form seeded by an earlier sample load, which seeding alone would keep.
    useBundledResponses();
    vi.mocked(saveBuildEvolveproToStorage).mockClear();
    vi.mocked(loadBuildEvolveproFromStorage).mockReturnValueOnce(
      { verdictXlsx: previous } as ReturnType<typeof loadBuildEvolveproFromStorage>,
    );

    // When sample data loads again.
    await makeStore({ formStoragePath: "/sample" }).loadSampleData();

    // Then the form names the original run's copy, which the evidence panel matches.
    expect(saveBuildEvolveproToStorage).toHaveBeenCalledWith(
      expect.objectContaining({ verdictXlsx: "/sample/sample_data/mame/original/13_mame_verdict.xlsx" }),
      "/sample",
    );
  });

  it("keeps a verdict workbook the user picked when sample data loads", async () => {
    // Given a form holding a workbook outside every sample location.
    useBundledResponses();
    vi.mocked(saveBuildEvolveproToStorage).mockClear();
    vi.mocked(loadBuildEvolveproFromStorage).mockReturnValueOnce(
      { verdictXlsx: "/data/my_verdict.xlsx" } as ReturnType<typeof loadBuildEvolveproFromStorage>,
    );

    // When sample data loads.
    await makeStore({ formStoragePath: "/sample" }).loadSampleData();

    // Then the user's choice is not overwritten.
    expect(saveBuildEvolveproToStorage).not.toHaveBeenCalled();
  });

  it("stores a Windows project copy path that round-trips to the original run output", async () => {
    // Given the real form storage and a Windows project folder.
    const actual = await vi.importActual<typeof import("@/lib/mame/buildEvolveproFormStorage")>(
      "@/lib/mame/buildEvolveproFormStorage",
    );
    vi.mocked(loadBuildEvolveproFromStorage).mockImplementation(actual.loadBuildEvolveproFromStorage);
    vi.mocked(saveBuildEvolveproToStorage).mockImplementation(actual.saveBuildEvolveproToStorage);
    vi.mocked(seedBuildEvolveproForm).mockImplementation(actual.seedBuildEvolveproForm);
    useBundledResponses();
    const project = "C:\\Users\\lab\\kuma\\demo";
    const store = makeStore({ projectPath: project, formStoragePath: project });
    try {
      // When sample data loads.
      await store.loadSampleData();

      // Then the step 4 form restores exactly the path the evidence panel compares against.
      const output = store.analyzeResult?.output_path;
      expect(output).toBe(`${project}\\sample_data\\mame\\original\\13_mame_verdict.xlsx`);
      expect(actual.loadBuildEvolveproFromStorage(project).verdictXlsx).toBe(output);
    } finally {
      vi.mocked(loadBuildEvolveproFromStorage).mockImplementation(
        () => ({ verdictXlsx: "" }) as ReturnType<typeof loadBuildEvolveproFromStorage>,
      );
      vi.mocked(saveBuildEvolveproToStorage).mockImplementation(() => undefined);
      vi.mocked(seedBuildEvolveproForm).mockImplementation(() => undefined);
      localStorage.clear();
    }
  });

  it("leaves both runs unloaded and reports the failure when the project copy fails", async () => {
    // Given a project folder that rejects copies.
    useBundledResponses();
    vi.mocked(copyFile).mockRejectedValue(new Error("disk full"));
    const store = makeStore({ formStoragePath: "/sample" });

    try {
      // When sample data loads.
      await store.loadSampleData();

      // Then no writable output falls back to the bundled resource path.
      expect(store.analyzeResult).toBeNull();
      expect(resequenceStore.getState().analyzeResult).toBeNull();
      expect(store.analyzeMessage).toContain("13_mame_verdict.xlsx (copy to project failed)");
    } finally {
      vi.mocked(copyFile).mockResolvedValue(undefined);
    }
  });
});
