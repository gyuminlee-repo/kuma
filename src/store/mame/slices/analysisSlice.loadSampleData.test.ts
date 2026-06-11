/**
 * analysisSlice.loadSampleData.test.ts
 *
 * MAME loadSampleData() 동작 검증:
 * - resolveResource 12개 경로 호출 (Phase 1 setup prefill seeds + EVOLVEpro form + fixture 포함)
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
vi.mock("@tauri-apps/plugin-fs", () => ({
  readTextFile: vi.fn(() => Promise.resolve("{}")),
}));

// seedBuildEvolveproForm touches localStorage; mock to avoid jsdom side-effects in unit tests
vi.mock("@/lib/mame/buildEvolveproFormStorage", () => ({
  seedBuildEvolveproForm: vi.fn(),
}));

import { resolveResource } from "@tauri-apps/api/path";
import {
  sampleReplicates,
  sampleSummary,
  sampleVerdicts,
  sampleWells,
} from "@/lib/mame/sampleData";
import { useRoundStore } from "@/store/round/roundSlice";
import type { AppState } from "../types";
import { createAnalysisSlice } from "./analysisSlice";

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = {
    referencePath: "",
    expectedPath: "",
    sampleMapPath: "",
    rawRunParams: {
      customBarcodesPath: "",
      sequencingSummaryPath: "",
      minQscore: 0,
      lengthMin: 0,
      lengthMax: 0,
      targetLength: null,
      lengthToleranceBp: 0,
      normalizeHeaders: false,
    } as AppState["rawRunParams"],
    validationErrors: [],
    analyzeMessage: "",
    setReferencePath: vi.fn((p: string) => {
      state.referencePath = p;
    }),
    setExpectedPath: vi.fn((p: string) => {
      state.expectedPath = p;
    }),
    setSampleMapPath: vi.fn((p: string) => {
      state.sampleMapPath = p;
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
  });

  it("resolves 8 bundled resources, creates round + WT-well plate meta, calls activity RPCs, populates input + results", async () => {
    // activity.upload returns records + plate_meta; hydrated into round.activity
    mockSendRequest.mockImplementation((method: string) => {
      if (method === "activity.upload") {
        return Promise.resolve({
          records: [
            { plate_id: "plate01", well_id: "A1", value: 1.011, replicate_idx: 1, is_wt: true },
          ],
          plate_meta: {
            plates: [
              { plate_id: "plate01", wt_wells: ["A1", "A2", "A3"], control_wells: [] },
            ],
          },
        });
      }
      return Promise.resolve({});
    });
    const store = makeStore();

    await store.loadSampleData();

    // 1. resolveResource 12번 (Phase 1 setup prefill + EVOLVEpro form seeds + analysis fixture)
    const expectedPaths = [
      "samples/mame/reference.fasta",
      "samples/mame/03_mame_expected_mutations.xlsx",
      "samples/mame/04_mame_custom_barcodes.xlsx",
      "samples/mame/05_mame_sample_map.xlsx",
      "samples/mame/06_mame_plate_layout.xlsx",
      "samples/mame/07_mame_activity_long.csv",
      "samples/mame/02_mame_barcode_seeds.xlsx",
      "samples/mame/egfp_with_flanks.fa",
      "samples/mame/08_mame_evolvepro_raw.xlsx",
      "samples/mame/09_mame_agilent_rep_batch.xlsx",
      "samples/mame/10_mame_gc_prenormalised.xlsx",
      "samples/mame/sample_analysis_result.json",
    ];
    expect(resolveResource).toHaveBeenCalledTimes(12);
    for (const p of expectedPaths) {
      expect(resolveResource).toHaveBeenCalledWith(p);
    }

    // 2. Round created in roundStore with sample WT-well plate meta
    const roundState = useRoundStore.getState();
    expect(roundState.rounds.length).toBe(1);
    const round = roundState.rounds[0]!;
    expect(round.plate_meta.plates).toEqual([
      { plate_id: "plate01", wt_wells: ["A1", "A2", "A3"], control_wells: [] },
    ]);
    expect(roundState.active_round_id).toBe(round.id);

    // 3. activity.set_plate_meta RPC uses the freshly created round id + WT wells
    expect(mockSendRequest).toHaveBeenCalledWith(
      "activity.set_plate_meta",
      expect.objectContaining({
        round_id: round.id,
        plate_meta: expect.objectContaining({
          plates: [
            { plate_id: "plate01", wt_wells: ["A1", "A2", "A3"], control_wells: [] },
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
    expect(round.activity?.plate_meta.plates[0]?.wt_wells).toEqual([
      "A1",
      "A2",
      "A3",
    ]);
    expect(round.activity?.records.length).toBeGreaterThan(0);

    // 4. 입력 경로 store populated
    expect(store.referencePath).toBe("/resolved/samples/mame/reference.fasta");
    expect(store.expectedPath).toBe(
      "/resolved/samples/mame/03_mame_expected_mutations.xlsx",
    );
    expect(store.sampleMapPath).toBe(
      "/resolved/samples/mame/05_mame_sample_map.xlsx",
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

    // 6. 성공 메시지
    expect(store.analyzeMessage).toMatch(/loaded/i);
    expect(store.analyzeMessage).not.toMatch(/activity RPC unavailable/);
  });

  it("falls back to mock results when activity RPC throws", async () => {
    mockSendRequest.mockRejectedValueOnce(new Error("sidecar down"));
    const store = makeStore();

    await store.loadSampleData();

    // 입력 경로 여전히 설정됨
    expect(store.referencePath).toBe("/resolved/samples/mame/reference.fasta");
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
});
