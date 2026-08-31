/**
 * analysisSlice.sampleDataStorage.test.ts
 *
 * Regression coverage for two loadSampleData defects fixed alongside this
 * file (see AGENTS.md task notes, "MAME sample data triplicate"):
 *
 * 1. Step-4 seeding must reach `formStoragePath` (the same key
 *    BuildEvolveproInputPanel reads via `useKumaProject().path`, populated
 *    for scratch sessions too), not `projectPath` (which stays null for a
 *    scratch session because it also gates the result-snapshot file write).
 *    Before the fix, `seedBuildEvolveproForm(..., get().projectPath)` was a
 *    silent no-op for every scratch session.
 * 2. `sampleDataLoaded` must flip true once results are populated and back
 *    to false on `clearResults` (a real input change, a reset, or a project
 *    switch), so InputPanel's "sample has no run folder" notice does not
 *    outlive the sample results it describes.
 *
 * Deliberately does not assert on fixture shape (well count, verdict
 * classes, native barcode names): the sample bundle is being regenerated
 * concurrently by another change. Only the two behaviours above are new;
 * `analysisSlice.loadSampleData.test.ts` owns fixture-shape coverage.
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

vi.mock("@tauri-apps/plugin-fs", () => ({
  readTextFile: vi.fn(() => Promise.resolve("{}")),
}));

const mockSeedBuildEvolveproForm = vi.fn();
vi.mock("@/lib/mame/buildEvolveproFormStorage", () => ({
  seedBuildEvolveproForm: (...args: unknown[]) => mockSeedBuildEvolveproForm(...args),
}));

import { useRoundStore } from "@/store/round/roundSlice";
import type { AppState } from "../types";
import { createAnalysisSlice } from "./analysisSlice";

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
    projectPath: null,
    formStoragePath: null,
    setReferencePath: vi.fn((p: string) => {
      state.referencePath = p;
    }),
    setExpectedPath: vi.fn((p: string) => {
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
    updater: Partial<AppState> | ((current: AppState) => Partial<AppState>),
  ) => {
    const updates = typeof updater === "function" ? updater(state as AppState) : updater;
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

describe("mame analysisSlice.loadSampleData, storage key + sampleDataLoaded", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRoundStore.setState({ rounds: [], active_round_id: null });
  });

  it("seeds step 4 via formStoragePath, which stays populated for a scratch session where projectPath is null", async () => {
    // Mirrors a scratch project: useMameAutosave leaves `projectPath` null
    // (it gates the result-snapshot write) but bridges the context path into
    // `formStoragePath` unconditionally, because that is the key
    // BuildEvolveproInputPanel actually reads from (`useKumaProject().path`).
    const store = makeStore({
      projectPath: null,
      formStoragePath: "/scratch/session-abc",
    });

    await store.loadSampleData();

    expect(mockSeedBuildEvolveproForm).toHaveBeenCalledTimes(1);
    const [, storageKeyArg] = mockSeedBuildEvolveproForm.mock.calls[0]!;
    expect(storageKeyArg).toBe("/scratch/session-abc");
  });

  it("bumps buildEvolveproSeedEpoch after seeding so an already-mounted step-4 panel re-reads storage", async () => {
    const store = makeStore({ formStoragePath: "/project" });
    expect(store.buildEvolveproSeedEpoch).toBe(0);

    await store.loadSampleData();

    expect(store.buildEvolveproSeedEpoch).toBe(1);
  });

  it("sets sampleDataLoaded once results are populated, and clearResults drops it again", async () => {
    const store = makeStore({ formStoragePath: "/project" });
    expect(store.sampleDataLoaded).toBe(false);

    await store.loadSampleData();
    expect(store.sampleDataLoaded).toBe(true);

    // clearResults is the shared invalidation path (a real input change, a
    // reset, or a project switch all call it) -- the sample-only notice must
    // not survive any of them.
    store.clearResults();
    expect(store.sampleDataLoaded).toBe(false);
  });

  it("does not set sampleDataLoaded when a critical file fails to resolve", async () => {
    const { resolveResource } = await import("@tauri-apps/api/path");
    vi.mocked(resolveResource).mockRejectedValueOnce(new Error("resource missing"));
    const store = makeStore({ formStoragePath: "/project" });

    await store.loadSampleData();

    expect(store.sampleDataLoaded).toBe(false);
    expect(mockSeedBuildEvolveproForm).not.toHaveBeenCalled();
  });
});
