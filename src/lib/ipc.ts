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
let nextId = 1;
const pending = new Map<number, PendingRequest>();
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
  if (!("id" in msg) || msg.id === undefined) {
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

export async function spawnSidecar(): Promise<void> {
  if (child) return;

  const command = Command.sidecar("binaries/evolveproprimer-sidecar");

  command.stdout.on("data", (line: string) => {
    for (const part of line.split("\n")) {
      handleLine(part);
    }
  });

  command.stderr.on("data", (line: string) => {
    console.log("[sidecar]", line);
  });

  command.on("error", (error: string) => {
    console.error("[sidecar] error:", error);
    child = null;
  });

  command.on("close", (data: { code: number | null }) => {
    console.log("[sidecar] exited with code:", data.code);
    child = null;
    for (const [id, req] of pending) {
      req.reject(new Error("Sidecar process exited"));
      pending.delete(id);
    }
  });

  const spawned = await command.spawn();
  child = spawned;

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => {
      onReady = null;
      reject(new Error("Sidecar ready timeout (10s)"));
    }, 10000);
    onReady = () => {
      clearTimeout(timeout);
      resolve();
    };
  });
  onReady = null;
}

export function setProgressHandler(
  handler: ((p: ProgressNotification) => void) | null,
) {
  onProgress = handler;
}

export async function sendRequest<T>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  if (!child) {
    throw new Error("Sidecar not running. Call spawnSidecar() first.");
  }

  const id = nextId++;
  const request = JSON.stringify({
    jsonrpc: "2.0",
    id,
    method,
    params,
  });

  return new Promise<T>((resolve, reject) => {
    pending.set(id, {
      resolve: resolve as (v: unknown) => void,
      reject,
    });
    child!.write(request + "\n").catch((err: Error) => {
      pending.delete(id);
      reject(err);
    });
  });
}

export async function killSidecar(): Promise<void> {
  if (child) {
    await child.kill();
    child = null;
  }
}

export function isSidecarRunning(): boolean {
  return child !== null;
}
