/**
 * JSON-RPC communication layer for the Python sidecar.
 *
 * Uses Tauri shell plugin to spawn and communicate with
 * the Python sidecar process via stdin/stdout.
 */

import { Command, type Child } from "@tauri-apps/plugin-shell";
import type {
  JsonRpcResponse,
  JsonRpcNotification,
  ProgressNotification,
} from "../types/models";

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
};

let child: Child | null = null;
let spawnPromise: Promise<void> | null = null;
let nextId = 1;
const pending = new Map<number, PendingRequest>();
let stdoutBuffer = "";
let stderrBuffer = "";
// NOTE: Single global progress handler. Only one operation can receive progress
// events at a time. This is fine for the current single-design-at-a-time model.
// If multi-operation progress is ever needed, refactor to a Map<requestId, handler>.
let onProgress: ((p: ProgressNotification) => void) | null = null;
let onReady: (() => void) | null = null;

function handleLine(line: string) {
  if (!line.trim()) return;

  let msg: JsonRpcResponse | JsonRpcNotification;
  try {
    msg = JSON.parse(line);
  } catch {
    console.error("[ipc] Failed to parse sidecar output:", line);
    return;
  }

  // Notification (no id)
  if (!("id" in msg) || msg.id === undefined || msg.id === null) {
    const notif = msg as JsonRpcNotification;
    if (notif.method === "progress" && onProgress) {
      onProgress(notif.params as unknown as ProgressNotification);
    } else if (notif.method === "ready" && onReady) {
      onReady();
    }
    return;
  }

  // Response
  const resp = msg as JsonRpcResponse;
  const req = pending.get(resp.id!);
  if (!req) {
    console.warn("[ipc] No pending request for id:", resp.id);
    return;
  }
  pending.delete(resp.id!);

  if (resp.error) {
    req.reject(new Error(`[${resp.error.code}] ${resp.error.message}`));
  } else {
    req.resolve(resp.result);
  }
}

function drainChunkLines(
  chunk: string,
  buffer: string,
  onLine: (line: string) => void,
): string {
  const combined = buffer + chunk;
  const normalized = combined.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  const remainder = lines.pop() ?? "";
  for (const line of lines) {
    onLine(line);
  }
  return remainder;
}

function flushBufferedLine(
  buffer: string,
  onLine: (line: string) => void,
): string {
  if (buffer.trim()) {
    onLine(buffer);
  }
  return "";
}

function handleStderrLine(line: string) {
  if (!line.trim()) return;
  console.log("[sidecar]", line);
}

export async function spawnSidecar(): Promise<void> {
  if (child) return;
  if (spawnPromise) return spawnPromise;

  spawnPromise = (async () => {
    const command = Command.sidecar("binaries/kuro-sidecar");
    stdoutBuffer = "";
    stderrBuffer = "";

    command.stdout.on("data", (chunk: string) => {
      stdoutBuffer = drainChunkLines(chunk, stdoutBuffer, handleLine);
    });

    command.stderr.on("data", (chunk: string) => {
      stderrBuffer = drainChunkLines(chunk, stderrBuffer, handleStderrLine);
    });

    command.on("error", (error: string) => {
      stdoutBuffer = "";
      stderrBuffer = "";
      console.error("[sidecar] error:", error);
      child = null;
    });

    command.on("close", (data: { code: number | null }) => {
      stdoutBuffer = flushBufferedLine(stdoutBuffer, handleLine);
      stderrBuffer = flushBufferedLine(stderrBuffer, handleStderrLine);
      console.log("[sidecar] exited with code:", data.code);
      child = null;
      for (const [id, req] of pending) {
        req.reject(new Error("Sidecar process exited"));
        pending.delete(id);
      }
    });

    // Set up ready handler BEFORE spawn to avoid race condition:
    // sidecar may send "ready" before the await below yields control.
    const readyPromise = new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        onReady = null;
        if (child) {
          child.kill().catch(() => {});
          child = null;
        }
        reject(new Error("Sidecar ready timeout (10s)"));
      }, 10000);
      onReady = () => {
        clearTimeout(timeout);
        resolve();
      };
    });

    const spawned = await command.spawn();
    child = spawned;

    await readyPromise;
    onReady = null;
  })();

  try {
    await spawnPromise;
  } catch (err) {
    const proc = child as Child | null;
    child = null;
    spawnPromise = null;
    if (proc) {
      proc.kill().catch(() => {});
    }
    throw err;
  } finally {
    spawnPromise = null;
  }
}

export function setProgressHandler(
  handler: ((p: ProgressNotification) => void) | null,
) {
  onProgress = handler;
}

export async function sendRequest<T>(
  method: string,
  params: Record<string, unknown> = {},
  timeoutMs = 60_000,
): Promise<T> {
  if (!child) {
    await spawnSidecar();
  }

  const id = nextId++;
  const request = JSON.stringify({
    jsonrpc: "2.0",
    id,
    method,
    params,
  });

  return new Promise<T>((resolve, reject) => {
    // NOTE: This timeout only rejects the client-side promise — it does NOT
    // cancel the in-flight sidecar operation. Call the sidecar's
    // cancel_design RPC when the frontend needs to stop primer design.
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`RPC timeout: ${method} after ${timeoutMs}ms`));
    }, timeoutMs);

    pending.set(id, {
      resolve: (v) => {
        clearTimeout(timer);
        (resolve as (v: unknown) => void)(v);
      },
      reject: (e) => {
        clearTimeout(timer);
        reject(e);
      },
    });

    const proc = child;
    if (!proc) {
      clearTimeout(timer);
      pending.delete(id);
      reject(new Error("Sidecar not running"));
      return;
    }
    proc.write(request + "\n").catch((err: Error) => {
      clearTimeout(timer);
      pending.delete(id);
      reject(err);
    });
  });
}

export async function killSidecar(): Promise<void> {
  spawnPromise = null;
  stdoutBuffer = "";
  stderrBuffer = "";
  if (child) {
    const c = child;
    child = null;
    onReady = null;
    for (const [id, req] of pending) {
      req.reject(new Error("Sidecar killed"));
      pending.delete(id);
    }
    await c.kill();
  }
}

export async function cancelAndRespawn(): Promise<void> {
  await killSidecar();
  await spawnSidecar();
}

export function isSidecarRunning(): boolean {
  return child !== null;
}
