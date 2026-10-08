/**
 * `previewCodonTable`, `importCodonTable` and `exportCodonTable`.
 *
 * The transport is mocked one layer below `sendRequest` (`rawSidecarRpc`), the
 * same arrangement loadOrganisms uses, so the real RPC result guard runs
 * between the fixture and the slice. A payload the guard rejects in production
 * fails here too, which is the reason not to mock `sendRequest` itself.
 *
 * What is pinned:
 *   1. preview sends `dry_run: true` and import sends `dry_run: false` -- the
 *      one difference between them, and the reason the sentences shown before
 *      importing are the sentences the import produces,
 *   2. a successful import relists and then selects, in that order, which is
 *      saveCustomPolymerase's contract,
 *   3. a rejected import touches neither, because the sidecar wrote nothing
 *      and selecting the key would name a table that does not exist.
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

vi.mock("@tauri-apps/plugin-fs", () => ({ writeTextFile: vi.fn() }));

const DIGEST = "c".repeat(64);
// A fixture path, not a real user folder: the slice never builds this string,
// it only carries whatever the sidecar reported.
const FIXTURE_DIR = "/tmp/kuma-fixture/codon_tables";

function document(key: string): Record<string, unknown> {
  return {
    key,
    name: "Lab strain",
    taxid: null,
    source: "",
    genetic_code: 11,
    aliases: [],
    codons: { M: [["ATG", 1.0]] },
  };
}

function importResult(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ok: true,
    installed: true,
    key: "lab_strain",
    table_sha256: DIGEST,
    errors: [],
    warnings: [],
    normalizations: [],
    checks_performed: 214,
    codons_examined: 64,
    document: document("lab_strain"),
    path: `${FIXTURE_DIR}/lab_strain.json`,
    ...over,
  };
}

function makeStore() {
  const state: Record<string, unknown> = {
    organisms: [],
    organism: "ecoli",
    codonTableFailures: [],
    codonTableDir: null,
    statusMessage: "",
  };
  const set = (u: Record<string, unknown> | ((s: typeof state) => Record<string, unknown>)) => {
    Object.assign(state, typeof u === "function" ? u(state) : u);
  };
  const get = () => state as unknown as AppState;
  const slice = createSequenceSlice(
    set as Parameters<typeof createSequenceSlice>[0],
    get as Parameters<typeof createSequenceSlice>[1],
    {} as Parameters<typeof createSequenceSlice>[2],
  );
  Object.assign(state, slice, {
    organisms: [],
    organism: "ecoli",
    statusMessage: "",
  });
  return { state, slice };
}

const PARAMS = { format: "json" as const, key: "lab_strain", filepath: "/tmp/t.json" };

describe("previewCodonTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends dry_run and does not relist or select", async () => {
    mockRawSidecarRpc.mockResolvedValue(importResult({ installed: false, path: null }));
    const { state, slice } = makeStore();
    const report = await slice.previewCodonTable(PARAMS);

    expect(mockRawSidecarRpc).toHaveBeenCalledTimes(1);
    expect(mockRawSidecarRpc.mock.calls[0][1]).toBe("import_codon_table");
    expect(mockRawSidecarRpc.mock.calls[0][2]).toMatchObject({ dry_run: true });
    expect(report.ok).toBe(true);
    expect(state.organism).toBe("ecoli");
  });

  it("returns a rejection as a result rather than throwing", async () => {
    mockRawSidecarRpc.mockResolvedValue(
      importResult({
        ok: false,
        installed: false,
        table_sha256: null,
        document: null,
        path: null,
        errors: [{ code: "V9", params: { key: "ecoli", name: "Escherichia coli K-12" } }],
      }),
    );
    const { slice } = makeStore();
    const report = await slice.previewCodonTable({ ...PARAMS, key: "ecoli" });
    expect(report.ok).toBe(false);
    expect(report.errors.map((f) => f.code)).toEqual(["V9"]);
  });
});

describe("importCodonTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends, relists, then selects the new key", async () => {
    mockRawSidecarRpc.mockImplementation(
      (_a: unknown, method: string) =>
        method === "list_organisms"
          ? Promise.resolve({
              organisms: [
                {
                  key: "lab_strain",
                  name: "Lab strain",
                  taxid: null,
                  source: "user",
                  aliases: [],
                  cds_count: null,
                  table_sha256: DIGEST,
                  warnings: [],
                },
              ],
              failed: [],
              user_dir: FIXTURE_DIR,
            })
          : Promise.resolve(importResult()),
    );
    const { state, slice } = makeStore();
    const result = await slice.importCodonTable(PARAMS);

    expect(result.installed).toBe(true);
    const methods = mockRawSidecarRpc.mock.calls.map((c) => c[1]);
    expect(methods).toEqual(["import_codon_table", "list_organisms"]);
    expect(mockRawSidecarRpc.mock.calls[0][2]).toMatchObject({ dry_run: false });
    // The relist has to land before the selection, or the key being selected
    // is not yet in the list the dropdown renders.
    expect((state.organisms as { key: string }[]).map((o) => o.key)).toEqual([
      "lab_strain",
    ]);
    expect(state.organism).toBe("lab_strain");
  });

  it("leaves the selection alone when the table was rejected", async () => {
    mockRawSidecarRpc.mockResolvedValue(
      importResult({
        ok: false,
        installed: false,
        table_sha256: null,
        document: null,
        path: null,
        errors: [
          {
            code: "V10",
            params: {
              key: "lab_strain",
              name: "Lab strain",
              date: "2026-09-23",
              sha8: "cccccccc",
            },
          },
        ],
      }),
    );
    const { state, slice } = makeStore();
    const result = await slice.importCodonTable(PARAMS);

    expect(result.installed).toBe(false);
    expect(mockRawSidecarRpc.mock.calls.map((c) => c[1])).toEqual([
      "import_codon_table",
    ]);
    expect(state.organism).toBe("ecoli");
  });

  it("reports a transport failure and rethrows", async () => {
    mockRawSidecarRpc.mockRejectedValue(new Error("sidecar gone"));
    const { state, slice } = makeStore();
    await expect(slice.importCodonTable(PARAMS)).rejects.toThrow("sidecar gone");
    expect(state.statusMessage).toContain("sidecar gone");
    expect(state.organism).toBe("ecoli");
  });
});

describe("exportCodonTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns the path the sidecar wrote", async () => {
    mockRawSidecarRpc.mockResolvedValue({
      path: "/tmp/ecoli.csv",
      format: "csv",
      bytes: 2048,
    });
    const { state, slice } = makeStore();
    const path = await slice.exportCodonTable({
      key: "ecoli",
      format: "csv",
      filepath: "/tmp/ecoli.csv",
    });
    expect(path).toBe("/tmp/ecoli.csv");
    expect(mockRawSidecarRpc.mock.calls[0][1]).toBe("export_codon_table");
    expect(state.statusMessage).toContain("/tmp/ecoli.csv");
  });
});
