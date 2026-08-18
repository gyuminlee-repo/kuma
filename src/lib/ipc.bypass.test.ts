/**
 * The raw sidecar transport is not reachable from feature code, and the
 * validator table is therefore the only way a sidecar payload becomes a typed
 * value.
 *
 * `sendRequest` was never the only way to reach a sidecar. `rpc()` in
 * `src/lib/ipc.ts` was exported and used directly by twelve production call
 * sites, which cast the reply to a type with nothing checking it. `load_fasta`
 * was the clearest symptom: `store/slices/sequenceSlice.ts` called it through
 * the guarded client while `components/mame/panels/BarcodeSetupPanel.tsx`
 * called the same method through the raw transport.
 *
 * Two things keep it closed, and this file checks both:
 *
 *  1. A source scan, so a call site written next month cannot reintroduce the
 *     bypass quietly. This repo has no ESLint configuration, so a test is the
 *     enforcement mechanism available; `no-restricted-imports` would be the
 *     other one if a config is ever added.
 *  2. Payload checks proving the moved methods are genuinely validated now,
 *     rather than merely routed through a function that looks like it
 *     validates. Each case below fails against the pre-change code.
 */

import { describe, expect, it, vi } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const mocks = vi.hoisted(() => ({ rpc: vi.fn(), killSidecar: vi.fn() }));

vi.mock("./ipc", () => ({
  rawSidecarRpc: mocks.rpc,
  killSidecar: mocks.killSidecar,
  isSidecarRunning: vi.fn(),
}));

import { sendRequest as sendKuroRequest } from "./ipc-kuro";
import { sendRequest as sendMameRequest } from "./ipc-mame";
import { isRecord } from "@/types/validators";

const SRC = resolve(__dirname, "..");

/**
 * The only modules allowed to import the raw transport. Both are the guarded
 * clients themselves, which is the one place the unchecked cast has to happen.
 */
const ALLOWED = new Set([
  "lib/ipc.ts",
  "lib/ipc-kuro/index.ts",
  "lib/ipc-mame/index.ts",
]);

/**
 * `withFileTypes` matters here rather than being a style choice: this repo lives
 * on a Windows drive mounted into WSL, where a `statSync` per entry turned this
 * scan into 29 seconds under full-suite load. Reading the type from the single
 * directory read keeps it near a second.
 */
function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      sourceFiles(join(dir, entry.name), out);
    } else if (/\.tsx?$/.test(entry.name)) {
      out.push(join(dir, entry.name));
    }
  }
  return out;
}

describe("the raw sidecar transport is unreachable from feature code", () => {
  it("is imported only by the two guarded IPC clients", { timeout: 60_000 }, () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const rel = relative(SRC, file).split("\\").join("/");
      if (ALLOWED.has(rel)) continue;
      // Test files legitimately mock the transport module to intercept it.
      if (/\.test\.tsx?$/.test(rel)) continue;
      if (/\brawSidecarRpc\b/.test(readFileSync(file, "utf8"))) {
        offenders.push(rel);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("no longer exports the old habit-forming name", async () => {
    const mod = await vi.importActual<Record<string, unknown>>("./ipc");
    expect(mod.rpc).toBeUndefined();
    expect(typeof mod.rawSidecarRpc).toBe("function");
  });
});

describe("payloads from the moved call sites are now refused", () => {
  /**
   * `components/layout/StatusBar.tsx` and `components/mame/layout/StatusBar.tsx`
   * both polled `health_info` through the raw transport, and the method was
   * absent from the KURO `RpcMethod` table entirely, so no validator existed to
   * bypass. The status bar divides `rss_bytes` and renders it.
   */
  it("rejects a health_info reply whose rss_bytes is not a number (kuro)", async () => {
    mocks.rpc.mockResolvedValueOnce({ pid: 1, rss_bytes: "12MB", py_version: "3.12.1" });
    await expect(sendKuroRequest("health_info", {})).rejects.toThrow();
  });

  it("rejects a health_info reply whose rss_bytes is NaN (mame)", async () => {
    mocks.rpc.mockResolvedValueOnce({ pid: 1, rss_bytes: NaN, py_version: "3.12.1" });
    await expect(sendMameRequest("health_info", {})).rejects.toThrow();
  });

  it("accepts the health_info reply both dispatchers actually build", async () => {
    const real = { pid: 4242, rss_bytes: 0, py_version: "3.12.1" };
    mocks.rpc.mockResolvedValueOnce(real);
    await expect(sendKuroRequest("health_info", {})).resolves.toEqual(real);
    mocks.rpc.mockResolvedValueOnce(real);
    await expect(sendMameRequest("health_info", {})).resolves.toEqual(real);
  });

  /**
   * `store/slices/settingsSlice.ts` called `settings_load` raw, and the
   * validator it skipped was `"settings" in value`, which accepts this. The
   * slice then reads `response.settings.theme` and writes it to localStorage.
   */
  it("rejects settings_load with a null settings bundle", async () => {
    mocks.rpc.mockResolvedValueOnce({ settings: null });
    await expect(sendKuroRequest("settings_load", {})).rejects.toThrow();
  });

  it("rejects settings_load with a theme outside the three literals", async () => {
    mocks.rpc.mockResolvedValueOnce({ settings: { theme: "midnight" } });
    await expect(sendKuroRequest("settings_load", {})).rejects.toThrow();
  });

  /**
   * The exact payload `handle_load({})` produces on a machine with no
   * preferences file, captured by running
   * `python-core/sidecar_kuro/handlers/settings.py` against a temp path. This is
   * the accept case that keeps the guard above from drifting into something
   * stricter than the handler.
   */
  it("accepts the settings_load payload the handler actually produces", async () => {
    const real = {
      settings: {
        language: "en",
        theme: "auto",
        default_workspace_folder: null,
        network: {
          offline_mode: false,
          consent_uniprot: true,
          consent_blast: true,
          consent_alphafold: true,
          consent_interpro: true,
        },
        sidecar: {
          concurrency_default: 4,
          cancel_timeout_secs: 30,
          persist_on_cancel: "partial",
        },
        telemetry: { crash_log_auto_send: false, anonymous_stats: false },
      },
    };
    mocks.rpc.mockResolvedValueOnce(real);
    await expect(sendKuroRequest("settings_load", {})).resolves.toEqual(real);
  });

  it("accepts a settings bundle with fields omitted, since Pydantic defaults them", async () => {
    mocks.rpc.mockResolvedValueOnce({ settings: {} });
    await expect(sendKuroRequest("settings_load", {})).resolves.toEqual({ settings: {} });
  });

  /** The old body was `"ok" in value && "path" in value`. */
  it("rejects settings_save whose path is null", async () => {
    mocks.rpc.mockResolvedValueOnce({ ok: false, path: null });
    await expect(sendKuroRequest("settings_save", { settings: {} })).rejects.toThrow();
  });

  /**
   * `components/widgets/ExportPlatePreview.tsx` called both dry runs raw. The
   * validators it skipped hand-inlined `typeof x === "number"`, so NaN passed,
   * and checked rows with a bare `Array.isArray`, so any array passed. The
   * preview renders these numbers as plate wells.
   */
  it("rejects an echo dry run whose total is NaN", async () => {
    mocks.rpc.mockResolvedValueOnce({ rows: [], total: NaN, transfer_vol: 100 });
    await expect(
      sendKuroRequest("export_echo_mapping_dry_run", {}),
    ).rejects.toThrow();
  });

  it("rejects an echo dry run whose rows are not echo rows", async () => {
    mocks.rpc.mockResolvedValueOnce({
      rows: [{ source_plate: "Source [1]" }],
      total: 1,
      transfer_vol: 100,
    });
    await expect(
      sendKuroRequest("export_echo_mapping_dry_run", {}),
    ).rejects.toThrow();
  });

  it("rejects a janus dry run whose row volume is Infinity", async () => {
    mocks.rpc.mockResolvedValueOnce({
      rows: [
        {
          name: "A1G-F",
          type: "primer",
          no: 1,
          asp_rack: "fw plate",
          asp_posi: "A1",
          dsp_rack: "PCR mixture plate",
          dsp_posi: "A1",
          volume: Infinity,
          mutation: "A1G",
          role: "fwd",
        },
      ],
      total: 1,
      transfer_vol: 2.0,
    });
    await expect(
      sendKuroRequest("export_janus_mapping_dry_run", {}),
    ).rejects.toThrow();
  });

  /**
   * `screens/MameTab.tsx` called `read_kuma_meta` raw. `null` is a genuine
   * success answer here (no `__kuma_meta__` sheet), so it must pass; a partial
   * dict must not, because the handler never emits one.
   */
  it("accepts a null read_kuma_meta result", async () => {
    mocks.rpc.mockResolvedValueOnce(null);
    await expect(sendMameRequest("read_kuma_meta", { path: "/tmp/x.xlsx" })).resolves.toBeNull();
  });

  it("rejects a read_kuma_meta result carrying only project_id", async () => {
    mocks.rpc.mockResolvedValueOnce({ project_id: "proj-1" });
    await expect(
      sendMameRequest("read_kuma_meta", { path: "/tmp/x.xlsx" }),
    ).rejects.toThrow();
  });

  /** `components/mame/panels/BarcodeSetupPanel.tsx`. */
  it("rejects an inspect_variant_source result whose headers is an array", async () => {
    mocks.rpc.mockResolvedValueOnce({
      is_kuro_export: false,
      sheets: [],
      headers: [],
      suggested_column: null,
    });
    await expect(
      sendMameRequest("inspect_variant_source", { path: "/tmp/v.csv" }),
    ).rejects.toThrow();
  });

  it("rejects a generate_mame_package result missing its warnings list", async () => {
    mocks.rpc.mockResolvedValueOnce({
      barcodes_xlsx: "/tmp/b.xlsx",
      amplicon_fa: "/tmp/a.fa",
      context_json: "/tmp/c.json",
      amplicon_length: null,
    });
    await expect(
      sendMameRequest("generate_mame_package", {}),
    ).rejects.toThrow();
  });
});

/**
 * `isRecord` is shared by every `Record<string, T>` guard in both validator
 * tables, and it used to be `typeof === "object" && !== null`, which is true for
 * arrays. `Object.values([])` is `[]`, so `.every(guard)` succeeded vacuously
 * and an array passed as a populated map.
 */
describe("isRecord distinguishes an object from an array", () => {
  it("rejects arrays and null, accepts plain objects", () => {
    expect(isRecord([])).toBe(false);
    expect(isRecord([1, 2])).toBe(false);
    expect(isRecord(null)).toBe(false);
    expect(isRecord({})).toBe(true);
    expect(isRecord({ a: 1 })).toBe(true);
  });
});
