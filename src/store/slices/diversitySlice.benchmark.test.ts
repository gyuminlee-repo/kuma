import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { sendRequest } from "../../lib/ipc-kuro";
import { createDiversitySlice } from "./diversitySlice";

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
}));

vi.mock("i18next", () => ({
  default: { t: (key: string) => key },
}));

const mockedSendRequest = vi.mocked(sendRequest);

function makeStore(overrides: Record<string, unknown> = {}) {
  const state: Record<string, unknown> = {
    statusMessage: "",
    yPredMap: { A2V: 0.9, K3R: 0.8, L4M: 0.7, T5S: 0.6 },
    refDomains: [],
    disabledDomains: [],
    seqInfo: null,
    selectedGene: "",
    maxPrimers: 2,
    benchmarkRandomTrials: 2,
    benchmarkTopPercentile: 10,
    benchmarkRandomSeed: null,
    domainStrategy: "proportional",
    maxPerPosition: 1,
    entropyWeightEnabled: false,
    entropyWeight: 0.3,
    paretoPoolMultiplier: 2,
  };
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u);
  };
  const get = () => state as unknown as AppState;
  const slice = createDiversitySlice(
    set as Parameters<typeof createDiversitySlice>[0],
    get as Parameters<typeof createDiversitySlice>[1],
    {} as Parameters<typeof createDiversitySlice>[2],
  );
  // The slice carries its own defaults, so the scenario is applied after it.
  Object.assign(state, slice, { distanceMode: "auto", structureAccession: "ESMFOLD:ABC", uniprotAccession: "", ...overrides });
  return { state, slice };
}

describe("runBenchmark distance notice", () => {
  beforeEach(() => mockedSendRequest.mockReset());

  it("says the benchmark ran on 1-D distance when a structure is set but its coordinates were not used", async () => {
    mockedSendRequest.mockResolvedValueOnce({ results: [], structure_coordinates_used: false } as never);
    const { state, slice } = makeStore();

    await slice.runBenchmark();

    expect(state.statusMessage).toContain("diversity.benchmarkOneDimensional");
  });

  it("adds no notice when the coordinates were used", async () => {
    mockedSendRequest.mockResolvedValueOnce({ results: [], structure_coordinates_used: true } as never);
    const { state, slice } = makeStore();

    await slice.runBenchmark();

    expect(state.statusMessage).not.toContain("diversity.benchmarkOneDimensional");
  });

  it("adds no notice when 1-D distance was the user's choice", async () => {
    mockedSendRequest.mockResolvedValueOnce({ results: [], structure_coordinates_used: false } as never);
    const { state, slice } = makeStore({ distanceMode: "1d" });

    await slice.runBenchmark();

    expect(state.statusMessage).not.toContain("diversity.benchmarkOneDimensional");
  });
});
