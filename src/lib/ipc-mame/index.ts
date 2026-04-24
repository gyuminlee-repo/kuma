import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { killSidecar as killSidecarRpc, rpc } from "../ipc";
import type { ProgressNotification } from "./types";

type ProgressEventPayload = {
  kind: "kuro" | "mame";
  params: ProgressNotification;
};

let running = false;
let progressHandler: ((p: ProgressNotification) => void) | null = null;
let progressUnlisten: UnlistenFn | null = null;
let subscribePromise: Promise<void> | null = null;

function hasTauriBridge(): boolean {
  return typeof (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !== "undefined";
}

async function ensureProgressListener() {
  if (!hasTauriBridge()) return;
  if (progressUnlisten || subscribePromise) return;
  subscribePromise = (async () => {
    progressUnlisten = await listen<ProgressEventPayload>(
      "sidecar://progress",
      (event) => {
        if (event.payload.kind === "mame" && progressHandler) {
          progressHandler(event.payload.params);
        }
      },
    );
  })().finally(() => {
    subscribePromise = null;
  });
  await subscribePromise;
}

export async function spawnSidecar(): Promise<void> {
  await ensureProgressListener();
}

export function setProgressHandler(
  handler: ((p: ProgressNotification) => void) | null,
) {
  progressHandler = handler;
  if (handler) {
    void ensureProgressListener();
    return;
  }
  if (progressUnlisten) {
    progressUnlisten();
    progressUnlisten = null;
  }
}

export async function sendRequest<T>(
  method: string,
  params: Record<string, unknown> = {},
  timeoutMs = 60_000,
): Promise<T> {
  const request = rpc<T>("mame", method, params);
  const timeout = new Promise<never>((_, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`RPC timeout: ${method} after ${timeoutMs}ms`));
    }, timeoutMs);
    void request.finally(() => clearTimeout(timer));
  });

  const result = await Promise.race([request, timeout]);
  running = true;
  return result;
}

export async function killSidecar(): Promise<void> {
  running = false;
  await killSidecarRpc("mame");
}

export async function cancelAndRespawn(): Promise<void> {
  await killSidecar();
  await spawnSidecar();
}

export function isSidecarRunning(): boolean {
  return running;
}
