/**
 * `loadOrganisms`: unwrapping the `list_organisms` envelope into the store.
 *
 * The transport is mocked one layer below `sendRequest` (`rawSidecarRpc` in
 * src/lib/ipc.ts), so the real RPC guard runs between the fixture and the
 * slice. Mocking `sendRequest` itself would let this file and
 * validators.listOrganisms.test.ts both pass on payloads the guard rejects in
 * production, which is the one arrangement neither file would catch.
 *
 * Three properties are pinned:
 *   1. a normal answer puts organisms, `failed` and `user_dir` in the store,
 *   2. a non-empty `failed` does not stop the organisms that did load from
 *      arriving - the whole point of per-file failure reporting (D2), and
 *   3. an RPC that throws leaves the previous lists alone and reports through
 *      `statusMessage`, which is the pre-change behaviour.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createSequenceSlice } from "./sequenceSlice";

const mockRawSidecarRpc = vi.hoisted(() => vi.fn());

vi.mock("@/lib/ipc", () => ({
  rawSidecarRpc: mockRawSidecarRpc,
  killSidecar: vi.fn(),
  isSidecarRunning: vi.fn(),
}));

function organism(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key: "ecoli",
    name: "Escherichia coli K-12",
    taxid: 511145,
    source: "builtin",
    aliases: ["e_coli"],
    cds_count: 14,
    table_sha256: "a".repeat(64),
    warnings: [],
    ...over,
  };
}

const USER_DIR = "/home/u/.local/share/kuma/codon_tables";

function makeStore(overrides: Partial<AppState> = {}) {
  const fixture: Record<string, unknown> = {
    organisms: [],
    codonTableFailures: [],
    codonTableDir: null,
    statusMessage: "",
    ...overrides,
  };
  const state: Record<string, unknown> = { ...fixture };
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u);
  };
  const get = () => state as unknown as AppState;
  const slice = createSequenceSlice(
    set as Parameters<typeof createSequenceSlice>[0],
    get as Parameters<typeof createSequenceSlice>[1],
    {} as Parameters<typeof createSequenceSlice>[2],
  );
  // The slice's own initial state would otherwise clobber the fixture.
  Object.assign(state, slice, fixture);
  return { state, slice };
}

describe("loadOrganisms envelope unwrapping", () => {
  beforeEach(() => vi.clearAllMocks());

  it("CONTROL asks the sidecar for list_organisms", async () => {
    mockRawSidecarRpc.mockResolvedValue({ organisms: [], failed: [], user_dir: USER_DIR });
    const { slice } = makeStore();
    await slice.loadOrganisms();
    expect(mockRawSidecarRpc).toHaveBeenCalledTimes(1);
    expect(mockRawSidecarRpc.mock.calls[0][1]).toBe("list_organisms");
  });

  it("puts organisms, failures and the resolved folder in the store", async () => {
    const user = organism({
      key: "example_strain",
      name: "Example strain (rename me)",
      taxid: null,
      source: "user",
      aliases: [],
      cds_count: null,
      table_sha256: "b".repeat(64),
      warnings: [{ code: "V32", params: {} }],
    });
    mockRawSidecarRpc.mockResolvedValue({
      organisms: [organism(), user],
      failed: [],
      user_dir: USER_DIR,
    });
    const { state, slice } = makeStore();
    await slice.loadOrganisms();
    expect((state.organisms as unknown[]).map((o) => (o as { key: string }).key))
      .toEqual(["ecoli", "example_strain"]);
    expect(state.codonTableFailures).toEqual([]);
    expect(state.codonTableDir).toBe(USER_DIR);
    expect(state.statusMessage).toBe("");
  });

  it("keeps loading organisms when some files failed", async () => {
    const failed = [
      {
        filename: "ecoli.json",
        code: "R5",
        reason:
          "ecoli.json is shadowed by the built-in table 'ecoli' and was not "
          + "loaded. Rename it to ecoli_lab.json to use it.",
      },
      { filename: "broken.json", code: "V17", reason: "Expected 21 amino acid entries." },
    ];
    mockRawSidecarRpc.mockResolvedValue({
      organisms: [organism()],
      failed,
      user_dir: USER_DIR,
    });
    const { state, slice } = makeStore();
    await slice.loadOrganisms();
    expect(state.organisms).toHaveLength(1);
    expect(state.codonTableFailures).toEqual(failed);
    expect(state.codonTableDir).toBe(USER_DIR);
    // A failed file is not an error for the call as a whole.
    expect(state.statusMessage).toBe("");
  });

  it("replaces a previous listing rather than appending to it (refresh)", async () => {
    mockRawSidecarRpc.mockResolvedValue({
      organisms: [organism()],
      failed: [],
      user_dir: USER_DIR,
    });
    const { state, slice } = makeStore({
      organisms: [organism({ key: "stale" })],
      codonTableFailures: [{ filename: "gone.json", code: "V17", reason: "old" }],
      codonTableDir: "/old/path",
    } as unknown as Partial<AppState>);
    await slice.loadOrganisms();
    expect((state.organisms as unknown[]).map((o) => (o as { key: string }).key)).toEqual(["ecoli"]);
    expect(state.codonTableFailures).toEqual([]);
    expect(state.codonTableDir).toBe(USER_DIR);
  });

  it("reports through statusMessage and keeps the old lists when the RPC rejects", async () => {
    mockRawSidecarRpc.mockRejectedValue(new Error("sidecar not running"));
    const previous = [organism({ key: "kept" })];
    const { state, slice } = makeStore({ organisms: previous } as unknown as Partial<AppState>);
    await expect(slice.loadOrganisms()).resolves.toBeUndefined();
    expect(state.statusMessage).toMatch(/Organism list load failed/);
    expect(state.statusMessage).toMatch(/sidecar not running/);
    expect(state.organisms).toBe(previous);
    expect(state.codonTableDir).toBeNull();
  });

  it("reports through statusMessage when the sidecar answers the pre-change bare array", async () => {
    // The guard rejects it inside sendRequest, so the slice sees a throw and
    // must not leave the store holding an undefined organism list.
    mockRawSidecarRpc.mockResolvedValue([organism()]);
    const { state, slice } = makeStore();
    await slice.loadOrganisms();
    expect(state.organisms).toEqual([]);
    expect(state.codonTableDir).toBeNull();
    expect(state.statusMessage).toMatch(/Organism list load failed/);
  });

  it("reports through statusMessage when one organism in the envelope is malformed", async () => {
    mockRawSidecarRpc.mockResolvedValue({
      organisms: [organism(), organism({ key: "bad", source: "built-in" })],
      failed: [],
      user_dir: USER_DIR,
    });
    const { state, slice } = makeStore();
    await slice.loadOrganisms();
    expect(state.organisms).toEqual([]);
    expect(state.statusMessage).toMatch(/Organism list load failed/);
  });
});
