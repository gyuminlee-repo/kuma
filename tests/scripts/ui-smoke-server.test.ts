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
import { createServer as createTcpServer } from "node:net";
import type { AddressInfo } from "node:net";
import { spawn, type ChildProcess } from "node:child_process";

import { afterEach, describe, expect, it } from "vitest";
import { assertStillRunning, startOwnedServer, stopServer } from "../../scripts/ui-smoke-server.mjs";

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

  it("counts a listener that accepts and never answers as taken", async () => {
    const port = await freePort();
    const silent = createTcpServer(() => {});
    await new Promise<void>((done) => silent.listen(port, "127.0.0.1", done));
    cleanups.push(() => silent.close());

    await expect(
      startOwnedServer({
        command: process.execPath,
        args: ["-e", serveScript(port)],
        url: `http://127.0.0.1:${port}`,
        timeoutMs: 5000,
      }),
    ).rejects.toThrow(/already served by another process/);
  });

  it("rejects within the deadline when its child accepts but never answers", async () => {
    const port = await freePort();
    const stall = `require("node:net").createServer(() => {}).listen(${port}, "127.0.0.1")`;
    const timeoutMs = 1500;
    const started = Date.now();

    await expect(
      startOwnedServer({
        command: process.execPath,
        args: ["-e", stall],
        url: `http://127.0.0.1:${port}`,
        timeoutMs,
      }),
    ).rejects.toThrow(/Timed out waiting for preview server/);
    // A fetch without an abort signal waits on the silent socket for minutes.
    expect(Date.now() - started).toBeLessThan(timeoutMs + 1000);
  });
});

describe("stopServer", () => {
  it("escalates to SIGKILL when the child ignores SIGTERM", async () => {
    const child: ChildProcess = spawn(
      process.execPath,
      ["-e", 'process.on("SIGTERM", () => {}); console.log("armed"); setInterval(() => {}, 1000);'],
      { stdio: ["ignore", "pipe", "inherit"] },
    );
    cleanups.push(() => child.kill("SIGKILL"));
    await new Promise<void>((done) => child.stdout?.once("data", () => done()));

    const started = Date.now();
    await expect(stopServer(child, { graceMs: 300 })).resolves.toBe(true);

    expect(child.exitCode !== null || child.signalCode !== null).toBe(true);
    if (process.platform !== "win32") expect(child.signalCode).toBe("SIGKILL");
    expect(Date.now() - started).toBeLessThan(3000);
  });

  it("returns at once for a child that has already exited", async () => {
    const child: ChildProcess = spawn(process.execPath, ["-e", "process.exit(0)"]);
    await new Promise((done) => child.once("exit", done));

    await expect(stopServer(child, { graceMs: 300 })).resolves.toBe(true);
  });
});
