import { Command, type Child } from "@tauri-apps/plugin-shell";
import type {
  JsonRpcNotification,
  JsonRpcResponse,
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
let onProgress: ((p: ProgressNotification) => void) | null = null;
let onReady: (() => void) | null = null;

function handleLine(line: string) {
  if (!line.trim()) return;

  let msg: JsonRpcResponse | JsonRpcNotification;
  try {
    msg = JSON.parse(line) as JsonRpcResponse | JsonRpcNotification;
  } catch {
    console.error("[ipc] Failed to parse sidecar output:", line);
    return;
  }

  if (!("id" in msg) || msg.id === undefined || msg.id === null) {
    const notif = msg as JsonRpcNotification;
    if (notif.method === "progress" && onProgress) {
      onProgress(notif.params as ProgressNotification);
    } else if (notif.method === "ready" && onReady) {
      onReady();
    }
    return;
  }

  const resp = msg as JsonRpcResponse;
  const responseId = resp.id;
  if (responseId === undefined) {
    return;
  }
  const req = pending.get(responseId);
  if (!req) {
    console.warn("[ipc] No pending request for id:", responseId);
    return;
  }
  pending.delete(responseId);

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

function flushBufferedLine(buffer: string, onLine: (line: string) => void): string {
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
    const command = Command.sidecar("binaries/mame-sidecar");
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

    const readyPromise = new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        onReady = null;
        if (child) {
          child.kill().catch(() => {});
          child = null;
        }
        reject(new Error("Sidecar ready timeout (10s)"));
      }, 10_000);
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
  } catch (error) {
    const proc: Child | null = child;
    child = null;
    spawnPromise = null;
    if (proc !== null) {
      (proc as Child).kill().catch(() => {});
    }
    throw error;
  } finally {
    spawnPromise = null;
  }
}

export function setProgressHandler(handler: ((p: ProgressNotification) => void) | null) {
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
  const request = JSON.stringify({ jsonrpc: "2.0", id, method, params });

  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`RPC timeout: ${method} after ${timeoutMs}ms`));
    }, timeoutMs);

    pending.set(id, {
      resolve: (value) => {
        clearTimeout(timer);
        resolve(value as T);
      },
      reject: (error) => {
        clearTimeout(timer);
        reject(error);
      },
    });

    const proc = child;
    if (!proc) {
      clearTimeout(timer);
      pending.delete(id);
      reject(new Error("Sidecar not running"));
      return;
    }

    proc.write(request + "\n").catch((error: unknown) => {
      clearTimeout(timer);
      pending.delete(id);
      reject(error instanceof Error ? error : new Error(String(error)));
    });
  });
}

export async function killSidecar(): Promise<void> {
  spawnPromise = null;
  stdoutBuffer = "";
  stderrBuffer = "";
  if (child) {
    const current = child;
    child = null;
    onReady = null;
    for (const [id, req] of pending) {
      req.reject(new Error("Sidecar killed"));
      pending.delete(id);
    }
    await current.kill();
  }
}

export async function cancelAndRespawn(): Promise<void> {
  await killSidecar();
  await spawnSidecar();
}

export function isSidecarRunning(): boolean {
  return child !== null;
}
