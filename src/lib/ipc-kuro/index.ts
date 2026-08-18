import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import i18next from "i18next";
import { killSidecar as killSidecarRpc, rawSidecarRpc } from "../ipc";
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
/** §1 Dead-lock 감지: 마지막 progress 이벤트 수신 timestamp(ms). */
let _lastProgressAt: number | null = null;

/** 마지막 kuro progress 수신 시각을 반환 (없으면 null). */
export function getLastProgressAt(): number | null {
  return _lastProgressAt;
}

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
          isProgressNotificationParams(event.payload.params)
        ) {
          _lastProgressAt = Date.now();
          if (onProgress) onProgress(event.payload.params);
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
  await rawSidecarRpc("kuro", "ping", {});
}

/**
 * Lazy-start probe for the kuro sidecar.
 *
 * The shell calls this when a tab becomes active. It exists so `MainShell` does
 * not have to import the raw transport to send one `ping`: the method has no
 * result worth validating (the dispatcher answers a literal `{"ok": true}`) and
 * no entry in the validator table, so it stays inside this module rather than
 * becoming a table method.
 *
 * Deliberately NOT `spawnSidecar`, which additionally attaches the progress
 * listener and returns early when the Tauri bridge is absent. This keeps the
 * exact behaviour the shell had through the raw transport, including rejecting
 * when there is no bridge.
 */
export async function pingSidecar(): Promise<void> {
  await rawSidecarRpc("kuro", "ping", {});
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
  const request = rawSidecarRpc<unknown>("kuro", method, params, timeoutMs);
  const timeout = new Promise<never>((_, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(i18next.t("ipcKuro.rpcTimeout", { method, timeoutMs })));
    }, timeoutMs);
    // The catch keeps the derived promise handled. Without it a rejecting request
    // raises an unhandled rejection on top of the error the caller already gets,
    // once per failed RPC. The rejection itself still reaches the caller below.
    void request.finally(() => clearTimeout(timer)).catch(() => {});
  });
  const result = await Promise.race([request, timeout]);
  if (!validateResult(result)) {
    throw new Error(i18next.t("ipcKuro.invalidResultShape", { method }));
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
