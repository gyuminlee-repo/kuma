import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { killSidecar as killSidecarRpc, rpc } from "../ipc";
import type {
  ProgressNotification,
  RpcMethod,
  RpcMethodMap,
  RpcMethodResult,
} from "../../types/models";
import {
  getRpcResultValidator,
  isProgressNotificationParams,
} from "../../types/validators";

type ProgressEventPayload = {
  kind: "kuro" | "mame";
  params: unknown;
};

let onProgress: ((p: ProgressNotification) => void) | null = null;
let running = false;
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
        if (
          event.payload.kind === "kuro" &&
          isProgressNotificationParams(event.payload.params) &&
          onProgress
        ) {
          onProgress(event.payload.params);
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
  if (!hasTauriBridge()) return;
  await rpc("kuro", "ping", {});
}

export function setProgressHandler(
  handler: ((p: ProgressNotification) => void) | null,
) {
  onProgress = handler;
  if (handler) {
    void ensureProgressListener();
    return;
  }
  if (progressUnlisten) {
    progressUnlisten();
    progressUnlisten = null;
  }
}

export async function sendRequest<K extends RpcMethod>(
  method: K,
  params: RpcMethodMap[K]["params"],
  timeoutMs = 60_000,
): Promise<RpcMethodMap[K]["result"]> {
  const validateResult = getRpcResultValidator(method);
  const request = rpc<unknown>("kuro", method, params);
  const timeout = new Promise<never>((_, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`RPC timeout: ${method} after ${timeoutMs}ms`));
    }, timeoutMs);
    void request.finally(() => clearTimeout(timer));
  });
  const result = await Promise.race([request, timeout]);
  if (!validateResult(result)) {
    throw new Error(`Invalid RPC result shape for ${method}`);
  }
  running = true;
  return result as RpcMethodResult<K>;
}

export async function killSidecar(): Promise<void> {
  running = false;
  await killSidecarRpc("kuro");
}

export async function cancelAndRespawn(): Promise<void> {
  await killSidecar();
  await spawnSidecar();
}

export function isSidecarRunning(): boolean {
  return running;
}
