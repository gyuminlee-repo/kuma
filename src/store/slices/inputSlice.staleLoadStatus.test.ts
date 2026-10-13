/**
 * loadEvolveproCsv writes "Loading EVOLVEpro file..." and then abandons the
 * response when the strict spatial context moved while the request was in
 * flight. The abandoned load must not leave that line in the status bar, but
 * only the newest load may clear it: an older one must not overwrite the line
 * of the load that replaced it, and a line some other action wrote meanwhile
 * is not ours to remove.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import type { EvolveproLoadResult } from "../../types/models";
import { strictSpatialFixture } from "@/test-utils/strictSpatialFixture";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@tauri-apps/api/path", () => ({ resolveResource: vi.fn() }));
vi.mock("i18next", () => ({ default: { t: (key: string) => key } }));

import { createInputSlice } from "./inputSlice";
import { sendRequest } from "@/lib/ipc-kuro";

const mockSend = vi.mocked(sendRequest);
const LOADING = "Loading EVOLVEpro file...";
const CHANGED = "strictSpatial.changedSelection";

const report = strictSpatialFixture();
const STRICT_RESULT: EvolveproLoadResult = {
  variants: [...report.selected_variants], y_preds: [2, 1],
  selected_count: 2, total_count: 4, strict_spatial: report,
};
const TOP_N_RESULT: EvolveproLoadResult = { variants: [], y_preds: [], total_count: 0, selected_count: 0 };

/** Each load_evolvepro_csv request waits here until the test answers it. */
function holdRequests() {
  const answers: Array<(result: EvolveproLoadResult) => void> = [];
  mockSend.mockImplementation(((method: string) => {
    if (method !== "load_evolvepro_csv") return Promise.reject(new Error(`unexpected ${method}`));
    return new Promise<EvolveproLoadResult>((resolve) => { answers.push(resolve); });
  }) as typeof sendRequest);
  return answers;
}

function makeStore(overrides: Record<string, unknown> = {}) {
  const state: Record<string, unknown> = {};
  const set = (update: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof update === "function" ? update(state) : update);
  };
  const get = () => state as unknown as AppState;
  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  );
  // Slice initial values go in first so the test values below win.
  Object.assign(state, slice, {
    mutationInputMode: "evolvepro", evolveproMode: "pipeline", evolveproScoreOrder: "desc",
    strictSpatialEnabled: true, structuralDiversityEnabled: true,
    strictSpatialBudgetMode: "unique_sites", strictSpatialSiteCap: null, strictSpatialSelection: null,
    positionDiversityEnabled: false, maxPerPosition: 1, domainDiversityEnabled: false,
    refDomains: [], disabledDomains: [], domainStrategy: "proportional", domainOverlapPolicy: "first",
    linkerHandling: "include", domainQuotaMin: 1, paretoDiversityEnabled: false,
    entropyWeightEnabled: false, entropyWeight: 0.3, paretoPoolMultiplier: 2, distanceMode: "auto",
    structuralKappa: 0.3, evolveproRound: 0, roundSize: 96, maxPrimers: 2,
    seqInfo: { genes: [{ cds_start: 1, translation: "MAAAAAAAAAAA" }] }, selectedGene: "1",
    structureAccession: "P12345", uniprotAccession: "", structureLoaded: true,
    requireNetworkConsent: async () => true,
    statusMessage: "Ready",
    ...overrides,
  });
  return { state, slice };
}

describe("loadEvolveproCsv status line when a strict load is abandoned", () => {
  // Braces: a returned mock would be run by vitest as a cleanup hook.
  beforeEach(() => { mockSend.mockReset(); });

  it("clears its loading line when the structure changes during the load", async () => {
    const answers = holdRequests();
    const { state, slice } = makeStore();
    const pending = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(1));
    expect(state.statusMessage).toBe(LOADING);
    state.structureAccession = "Q50L36";
    answers[0](STRICT_RESULT);
    await pending;
    expect(state.statusMessage).not.toBe(LOADING);
    expect(state.statusMessage).toBe(CHANGED);
    expect(state.strictSpatialSelection).toBeNull();
  });

  it("clears its loading line when strict mode is switched off during the load", async () => {
    const answers = holdRequests();
    const { state, slice } = makeStore();
    const pending = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(1));
    state.strictSpatialEnabled = false;
    answers[0](STRICT_RESULT);
    await pending;
    expect(state.statusMessage).toBe(CHANGED);
  });

  it("leaves the line of a newer load alone when an older load is abandoned", async () => {
    const answers = holdRequests();
    const { state, slice } = makeStore();
    const older = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(1));
    const newer = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(2));
    expect(state.statusMessage).toBe(LOADING);
    state.structureAccession = "Q50L36";
    answers[0](STRICT_RESULT);
    await older;
    expect(state.statusMessage).toBe(LOADING);
    // The newer load is the one that now finds its context changed.
    answers[1](STRICT_RESULT);
    await newer;
    expect(state.statusMessage).toBe(CHANGED);
  });

  it("does not remove a line another action wrote while the load was in flight", async () => {
    const answers = holdRequests();
    const { state, slice } = makeStore();
    const pending = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(1));
    state.statusMessage = "Sequence loaded";
    state.structureAccession = "Q50L36";
    answers[0](STRICT_RESULT);
    await pending;
    expect(state.statusMessage).toBe("Sequence loaded");
  });

  it("keeps the completion summary when a strict load finishes in its own context", async () => {
    const answers = holdRequests();
    const { state, slice } = makeStore();
    const pending = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(1));
    answers[0](STRICT_RESULT);
    await pending;
    expect(state.statusMessage).toBe("EVOLVEpro: 2/4 variants");
    expect(state.strictSpatialSelection).not.toBeNull();
  });

  it("keeps the completion summary of a load that never was strict", async () => {
    const answers = holdRequests();
    const { state, slice } = makeStore({ strictSpatialEnabled: false, evolveproMode: "topN" });
    const pending = slice.loadEvolveproCsv("/fake/file.csv");
    await vi.waitFor(() => expect(answers).toHaveLength(1));
    state.structureAccession = "Q50L36";
    answers[0](TOP_N_RESULT);
    await pending;
    expect(state.statusMessage).toBe("EVOLVEpro: 0/0 variants");
  });
});
