/**
 * JSON-RPC communication layer for the Python sidecar.
 *
 * Uses Tauri shell plugin to spawn and communicate with
 * the Python sidecar process via stdin/stdout.
 */

import { Command, type Child } from "@tauri-apps/plugin-shell";
import type {
  JsonRpcMessage,
  JsonRpcRequest,
  ProgressNotification,
  RpcMethod,
  RpcMethodMap,
  RpcMethodResult,
} from "../types/models";
import {
  getRpcResultValidator,
  isJsonRpcError,
  isProgressNotificationParams,
  isRecord,
} from "../types/validators";

type PendingRequest = {
  method: RpcMethod;
  resolveResult: (value: unknown) => void;
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

function getCurrentChild(): Child | null {
  return child;
}

function parseJsonRpcMessage(line: string): JsonRpcMessage | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }

  if (!isRecord(parsed) || parsed.jsonrpc !== "2.0") {
    return null;
  }

  if ("id" in parsed) {
    const { id } = parsed;
    if (typeof id !== "number" && id !== null) {
      return null;
    }

    if ("error" in parsed && parsed.error !== undefined) {
      if (!isJsonRpcError(parsed.error)) {
        return null;
      }
      return {
        jsonrpc: "2.0",
        id,
        error: parsed.error,
      };
    }

    if ("result" in parsed) {
      if (id === null) {
        return null;
      }
      return {
        jsonrpc: "2.0",
        id,
        result: parsed.result,
      };
    }

    return null;
  }

  if (parsed.method === "ready") {
    return {
      jsonrpc: "2.0",
      method: "ready",
      params: {},
    };
  }

  if (
    parsed.method === "progress" &&
    isProgressNotificationParams(parsed.params)
  ) {
    return {
      jsonrpc: "2.0",
      method: "progress",
      params: parsed.params,
    };
  }

  return null;
}

function createPendingRequest<K extends RpcMethod>(
  method: K,
  validateResult: (value: unknown) => value is RpcMethodResult<K>,
  resolve: (value: RpcMethodResult<K>) => void,
  reject: (reason: Error) => void,
  timer: ReturnType<typeof setTimeout>,
): PendingRequest {
  return {
    method,
    resolveResult: (value) => {
      clearTimeout(timer);
      if (!validateResult(value)) {
        reject(new Error(`Invalid RPC result shape for ${method}`));
        return;
      }
      resolve(value);
    },
    reject: (reason) => {
      clearTimeout(timer);
      reject(reason);
    },
  };
}

function handleLine(line: string) {
  if (!line.trim()) return;

  const msg = parseJsonRpcMessage(line);
  if (!msg) {
    console.error("[ipc] Failed to parse sidecar output:", line);
    return;
  }

  if (!("id" in msg)) {
    if (msg.method === "progress" && onProgress) {
      onProgress(msg.params);
    } else if (msg.method === "ready" && onReady) {
      onReady();
    }
    return;
  }

  if (msg.id === null) {
    console.warn("[ipc] Received response without request id");
    return;
  }

  const req = pending.get(msg.id);
  if (!req) {
    console.warn("[ipc] No pending request for id:", msg.id);
    return;
  }
  pending.delete(msg.id);

  if ("error" in msg && msg.error) {
    req.reject(new Error(`${req.method}: [${msg.error.code}] ${msg.error.message}`));
  } else {
    req.resolveResult(msg.result);
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
  console.debug("[sidecar]", line);
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
      if (data.code !== 0 && data.code !== null) {
        console.warn("[sidecar] exited with code:", data.code);
      }
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
    const killPromise = getCurrentChild()?.kill();
    child = null;
    spawnPromise = null;
    void killPromise?.catch(() => {});
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

export async function sendRequest<K extends keyof RpcMethodMap>(
  method: K,
  params: RpcMethodMap[K]["params"],
  timeoutMs = 60_000,
): Promise<RpcMethodMap[K]["result"]> {
  if (!child) {
    await spawnSidecar();
  }

  const id = nextId++;
  const requestPayload: JsonRpcRequest<K> = {
    jsonrpc: "2.0",
    id,
    method,
    params,
  };
  const request = JSON.stringify(requestPayload);

  return new Promise<RpcMethodMap[K]["result"]>((resolve, reject) => {
    // NOTE: This timeout only rejects the client-side promise — it does NOT
    // cancel the in-flight sidecar operation. Call the sidecar's
    // cancel_design RPC when the frontend needs to stop primer design.
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`RPC timeout: ${method} after ${timeoutMs}ms`));
    }, timeoutMs);

    pending.set(
      id,
      createPendingRequest(
        method,
        getRpcResultValidator(method),
        resolve,
        reject,
        timer,
      ),
    );

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
