/**
 * scripts/ui-smoke-server.mjs: the smoke must test a server it started.
 *
 * Readiness used to accept any 200 on the port, so another checkout's preview
 * holding 4173 made the smoke pass against the wrong page while the new
 * server exited on --strictPort. Every case uses a free ephemeral port and a
 * plain node child in place of vite.
 *
 * @vitest-environment node
 */
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import type { ChildProcess } from "node:child_process";

import { afterEach, describe, expect, it } from "vitest";
import { assertStillRunning, startOwnedServer } from "../../scripts/ui-smoke-server.mjs";

const cleanups: Array<() => void> = [];
afterEach(() => {
  while (cleanups.length) cleanups.pop()?.();
});

async function freePort(): Promise<number> {
  const probe = createServer();
  await new Promise<void>((done) => probe.listen(0, "127.0.0.1", done));
  const { port } = probe.address() as AddressInfo;
  await new Promise<void>((done) => probe.close(() => done()));
  return port;
}

function serveScript(port: number): string {
  return `require("node:http").createServer((q, r) => r.end("ok")).listen(${port}, "127.0.0.1")`;
}

describe("startOwnedServer", () => {
  it("refuses a port another process already serves", async () => {
    const port = await freePort();
    const other: Server = createServer((_q, r) => r.end("old checkout"));
    await new Promise<void>((done) => other.listen(port, "127.0.0.1", done));
    cleanups.push(() => other.close());

    await expect(
      startOwnedServer({
        command: process.execPath,
        args: ["-e", serveScript(port)],
        url: `http://127.0.0.1:${port}`,
        timeoutMs: 5000,
      }),
    ).rejects.toThrow(/already served by another process/);
  });

  it("rejects at once when the child exits before it is ready", async () => {
    const port = await freePort();
    const started = Date.now();

    await expect(
      startOwnedServer({
        command: process.execPath,
        args: ["-e", "process.exit(3)"],
        url: `http://127.0.0.1:${port}`,
        timeoutMs: 20000,
      }),
    ).rejects.toThrow(/exited before it was ready \(code 3/);
    expect(Date.now() - started).toBeLessThan(10000);
  });

  it("resolves with its own child and notices when that child dies", async () => {
    const port = await freePort();
    const child: ChildProcess = await startOwnedServer({
      command: process.execPath,
      args: ["-e", serveScript(port)],
      url: `http://127.0.0.1:${port}`,
      timeoutMs: 10000,
    });
    cleanups.push(() => child.kill("SIGKILL"));

    expect(() => assertStillRunning(child)).not.toThrow();
    child.kill("SIGKILL");
    await new Promise((done) => child.once("exit", done));
    expect(() => assertStillRunning(child)).toThrow(/exited during the smoke/);
  });
});
