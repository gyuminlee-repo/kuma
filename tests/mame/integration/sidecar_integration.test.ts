/**
 * End-to-end sidecar integration test (Tauri-less).
 *
 * Spawns the Python sidecar directly via child_process and drives it over
 * stdin/stdout JSON-RPC, exercising validate_inputs -> analyze ->
 * get_plate_data -> export_excel in sequence with the committed fixture set.
 *
 * Runs under `pnpm test:integration` with the dedicated vitest config so it
 * does not interfere with the frontend vitest pool.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const REPO_ROOT = resolve(__dirname, "..", "..");
const SIDECAR_ENTRY = resolve(REPO_ROOT, "python-core", "sidecar_main.py");
const FIXTURES = resolve(REPO_ROOT, "tests", "fixtures");

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
}

class SidecarClient {
  readonly proc: ChildProcessWithoutNullStreams;
  private buffer = "";
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (err: Error) => void }
  >();
  private readyResolvers: Array<() => void> = [];
  private ready = false;

  constructor(proc: ChildProcessWithoutNullStreams) {
    this.proc = proc;
    this.proc.stdout.setEncoding("utf8");
    this.proc.stdout.on("data", (chunk: string) => this.onStdout(chunk));
    this.proc.stderr.setEncoding("utf8");
    this.proc.stderr.on("data", (chunk: string) => {
      // Surface sidecar stderr for debugging test failures without failing the
      // test on informational logs.
      process.stderr.write(`[sidecar:stderr] ${chunk}`);
    });
  }

  private onStdout(chunk: string) {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let msg: JsonRpcResponse | JsonRpcNotification;
      try {
        msg = JSON.parse(trimmed) as JsonRpcResponse | JsonRpcNotification;
      } catch {
        process.stderr.write(`[sidecar:bad-json] ${trimmed}\n`);
        continue;
      }
      if ("id" in msg && msg.id !== undefined && msg.id !== null) {
        const waiter = this.pending.get(msg.id);
        if (!waiter) continue;
        this.pending.delete(msg.id);
        if (msg.error) {
          waiter.reject(
            new Error(`[${msg.error.code}] ${msg.error.message}`),
          );
        } else {
          waiter.resolve(msg.result);
        }
      } else if ((msg as JsonRpcNotification).method === "ready") {
        this.ready = true;
        const waiters = this.readyResolvers.splice(0);
        for (const r of waiters) r();
      }
      // progress notifications are ignored in this test
    }
  }

  waitReady(timeoutMs = 10_000): Promise<void> {
    if (this.ready) return Promise.resolve();
    return new Promise<void>((resolveFn, rejectFn) => {
      const t = setTimeout(() => {
        rejectFn(new Error("Sidecar ready timeout"));
      }, timeoutMs);
      this.readyResolvers.push(() => {
        clearTimeout(t);
        resolveFn();
      });
    });
  }

  request<T = unknown>(method: string, params: Record<string, unknown>): Promise<T> {
    const id = this.nextId++;
    const payload = JSON.stringify({ jsonrpc: "2.0", id, method, params });
    return new Promise<T>((resolveFn, rejectFn) => {
      this.pending.set(id, {
        resolve: (v) => resolveFn(v as T),
        reject: rejectFn,
      });
      this.proc.stdin.write(payload + "\n");
    });
  }

  async shutdown(): Promise<void> {
    if (this.proc.exitCode !== null) return;
    this.proc.kill("SIGTERM");
    await new Promise<void>((r) => {
      const t = setTimeout(() => {
        try {
          this.proc.kill("SIGKILL");
        } catch {
          /* ignore */
        }
        r();
      }, 5000);
      this.proc.on("exit", () => {
        clearTimeout(t);
        r();
      });
    });
  }
}

function pickPython(): string {
  return process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
}

describe("sidecar integration", () => {
  let client: SidecarClient;
  let workDir: string;

  beforeAll(async () => {
    workDir = mkdtempSync(join(tmpdir(), "ngs-integration-"));
    const proc = spawn(pickPython(), [SIDECAR_ENTRY], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
      },
    });
    client = new SidecarClient(proc);
    await client.waitReady(15_000);
  }, 30_000);

  afterAll(async () => {
    if (client) await client.shutdown();
    if (workDir) {
      try {
        rmSync(workDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    }
  });

  it("validates fixture inputs", async () => {
    const result = (await client.request<{
      valid?: boolean;
      errors?: string[];
    }>("validate_inputs", {
      input_dir: resolve(FIXTURES, "mock_consensus_output", "NB01"),
      reference: resolve(FIXTURES, "reference.fasta"),
      expected: resolve(FIXTURES, "KURO_test.xlsx"),
      cds_end: 750,
    })) as { valid?: boolean; errors?: string[] };

    // Accept either shape — spec allows {valid:true} or {errors:[]}
    const ok =
      result.valid === true ||
      (Array.isArray(result.errors) && result.errors.length === 0);
    expect(ok, `validate_inputs result=${JSON.stringify(result)}`).toBe(true);
  });

  it("runs analyze on fixture, producing verdicts + output xlsx", async () => {
    const outputPath = join(workDir, "analyze_output.xlsx");
    const result = (await client.request<Record<string, unknown>>("analyze", {
      input_dir: resolve(FIXTURES, "mock_consensus_output", "NB01"),
      reference: resolve(FIXTURES, "reference.fasta"),
      expected: resolve(FIXTURES, "KURO_test.xlsx"),
      output: outputPath,
      mode: "amplicon",
      ingest_mode: "barcode",
      cds_start: 0,
      cds_end: 750,
      min_file_size_kb: 50.0,
      many_cutoff: 5,
    })) as Record<string, unknown>;

    expect(result).toHaveProperty("verdicts");
    expect(result).toHaveProperty("replicates");
    expect(result).toHaveProperty("output_path");
    expect(result).toHaveProperty("summary");
    expect(Array.isArray(result.verdicts)).toBe(true);
    expect(existsSync(outputPath)).toBe(true);
  }, 120_000);

  it("returns well-shaped plate data", async () => {
    const result = (await client.request<{
      wells: Array<Record<string, unknown>>;
    }>("get_plate_data", {})) as { wells: Array<Record<string, unknown>> };

    expect(Array.isArray(result.wells)).toBe(true);
    // When the fixture produces verdicts, validate shape on the first well.
    // An empty array is still a well-shaped response for fixtures without
    // barcode matches, so do not assert non-empty.
    if (result.wells.length > 0) {
      const first = result.wells[0];
      expect(first).toHaveProperty("well");
      expect(first).toHaveProperty("barcode");
      expect(first).toHaveProperty("verdict");
    }
  });

  it("re-exports excel to a fresh path", async () => {
    const exportPath = join(workDir, "re_export.xlsx");
    const result = (await client.request<{ output_path: string }>(
      "export_excel",
      { output: exportPath },
    )) as { output_path: string };

    expect(result.output_path).toBe(exportPath);
    expect(existsSync(exportPath)).toBe(true);
  });
});
