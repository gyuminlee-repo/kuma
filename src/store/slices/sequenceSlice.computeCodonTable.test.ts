/**
 * `previewComputedCodonTable` and `computeCodonTable`.
 *
 * Built as the sibling of `sequenceSlice.importCodonTable.test.ts` and mocked
 * at the same layer: `rawSidecarRpc`, one below `sendRequest`, so the real
 * result guard runs between the fixture and the slice. That is the point of
 * the arrangement here more than on the import path, because the compute reply
 * carries a `preview` block the guard demands in full -- a sidecar that ran the
 * scan and dropped the tally must fail here the way it would fail in the app.
 *
 * What is pinned:
 *   1. the preview sends `dry_run: true` and the install sends `dry_run: false`,
 *   2. the genetic code the caller chose is the one that goes on the wire, with
 *      no default substituted for it,
 *   3. a successful compute relists and then selects, the order
 *      saveCustomPolymerase set and importCodonTable already follows,
 *   4. a rejected compute touches neither, because nothing was written,
 *   5. a reply whose preview is missing is rejected by the guard rather than
 *      reaching the dialog as a panel of blanks.
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

const DIGEST = "d".repeat(64);
const FIXTURE_DIR = "/tmp/kuma-fixture/codon_tables";

function preview(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    source_format: "fasta",
    cds_total: 6420,
    cds_counted: 6256,
    cds_excluded: { pseudo: 164 },
    excluded_examples: { pseudo: ["lcl|NC_012808.1_cds_0001"] },
    codon_count: 1930715,
    top_codons: [{ aa: "M", codon: "ATG", fraction: 1.0, count: 37776 }],
    reference_key: "ecoli",
    divergent_codons: [
      {
        aa: "A",
        codon: "GCC",
        fraction: 0.51,
        reference_fraction: 0.27,
        delta: 0.24,
      },
    ],
    ...over,
  };
}

function computeResult(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ok: true,
    installed: true,
    key: "am1_lab",
    table_sha256: DIGEST,
    errors: [],
    warnings: [],
    normalizations: [],
    checks_performed: 214,
    codons_examined: 64,
    document: {
      key: "am1_lab",
      name: "M. extorquens AM1",
      taxid: null,
      source: "",
      genetic_code: 11,
      aliases: [],
      codons: { M: [["ATG", 1.0]] },
    },
    path: `${FIXTURE_DIR}/am1_lab.json`,
    preview: preview(),
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
  Object.assign(state, slice, { organisms: [], organism: "ecoli", statusMessage: "" });
  return { state, slice };
}

const PARAMS = {
  filepath: "/tmp/cds_from_genomic.fna",
  key: "am1_lab",
  genetic_code: 11,
};

describe("previewComputedCodonTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends dry_run and does not relist or select", async () => {
    mockRawSidecarRpc.mockResolvedValue(
      computeResult({ installed: false, path: null }),
    );
    const { state, slice } = makeStore();
    const report = await slice.previewComputedCodonTable(PARAMS);

    expect(mockRawSidecarRpc).toHaveBeenCalledTimes(1);
    expect(mockRawSidecarRpc.mock.calls[0][1]).toBe("compute_codon_table");
    expect(mockRawSidecarRpc.mock.calls[0][2]).toMatchObject({ dry_run: true });
    expect(report.preview.cds_counted).toBe(6256);
    expect(state.organism).toBe("ecoli");
  });

  it("carries the tally through to the caller", async () => {
    mockRawSidecarRpc.mockResolvedValue(
      computeResult({ installed: false, path: null }),
    );
    const { slice } = makeStore();
    const report = await slice.previewComputedCodonTable(PARAMS);

    expect(report.preview.cds_excluded).toEqual({ pseudo: 164 });
    expect(report.preview.top_codons[0]).toMatchObject({ aa: "M", codon: "ATG" });
    expect(report.preview.reference_key).toBe("ecoli");
  });

  it("refuses a reply that dropped the preview", async () => {
    const { preview: _dropped, ...withoutPreview } = computeResult();
    mockRawSidecarRpc.mockResolvedValue(withoutPreview);
    const { slice } = makeStore();
    await expect(slice.previewComputedCodonTable(PARAMS)).rejects.toThrow();
  });

  it("returns a rejection as a result rather than throwing", async () => {
    mockRawSidecarRpc.mockResolvedValue(
      computeResult({
        ok: false,
        installed: false,
        table_sha256: null,
        document: null,
        path: null,
        errors: [{ code: "G3", params: { file: "empty.fna", total: 0 } }],
        preview: preview({
          cds_total: 0,
          cds_counted: 0,
          codon_count: 0,
          cds_excluded: {},
          excluded_examples: {},
          top_codons: [],
          divergent_codons: [],
          reference_key: null,
        }),
      }),
    );
    const { slice } = makeStore();
    const report = await slice.previewComputedCodonTable(PARAMS);
    expect(report.ok).toBe(false);
    expect(report.errors.map((f) => f.code)).toEqual(["G3"]);
  });
});

describe("computeCodonTable", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends the chosen genetic code unchanged", async () => {
    // Codes 1 and 11 count identically, so a substituted value shows up
    // nowhere except on the wire. This is the assertion that sees it.
    mockRawSidecarRpc.mockResolvedValue(
      computeResult({ installed: false, path: null }),
    );
    const { slice } = makeStore();
    await slice.previewComputedCodonTable({ ...PARAMS, genetic_code: 1 });
    expect(mockRawSidecarRpc.mock.calls[0][2]).toMatchObject({ genetic_code: 1 });
  });

  it("sends, relists, then selects the new key", async () => {
    mockRawSidecarRpc.mockImplementation(
      (_a: unknown, method: string) =>
        method === "list_organisms"
          ? Promise.resolve({
              organisms: [
                {
                  key: "am1_lab",
                  name: "M. extorquens AM1",
                  taxid: null,
                  source: "user",
                  aliases: [],
                  cds_count: 6256,
                  table_sha256: DIGEST,
                  warnings: [],
                },
              ],
              failed: [],
              user_dir: FIXTURE_DIR,
            })
          : Promise.resolve(computeResult()),
    );
    const { state, slice } = makeStore();
    const result = await slice.computeCodonTable(PARAMS);

    expect(result.installed).toBe(true);
    expect(mockRawSidecarRpc.mock.calls.map((c) => c[1])).toEqual([
      "compute_codon_table",
      "list_organisms",
    ]);
    expect(mockRawSidecarRpc.mock.calls[0][2]).toMatchObject({ dry_run: false });
    expect(state.organism).toBe("am1_lab");
  });

  it("leaves the selection alone when the table was rejected", async () => {
    mockRawSidecarRpc.mockResolvedValue(
      computeResult({
        ok: false,
        installed: false,
        table_sha256: null,
        document: null,
        path: null,
        errors: [{ code: "V10", params: { key: "am1_lab" } }],
      }),
    );
    const { state, slice } = makeStore();
    const result = await slice.computeCodonTable(PARAMS);

    expect(result.installed).toBe(false);
    expect(mockRawSidecarRpc.mock.calls.map((c) => c[1])).toEqual([
      "compute_codon_table",
    ]);
    expect(state.organism).toBe("ecoli");
  });

  it("reports a transport failure and rethrows", async () => {
    mockRawSidecarRpc.mockRejectedValue(new Error("sidecar gone"));
    const { state, slice } = makeStore();
    await expect(slice.computeCodonTable(PARAMS)).rejects.toThrow("sidecar gone");
    expect(String(state.statusMessage)).toContain("sidecar gone");
  });
});
