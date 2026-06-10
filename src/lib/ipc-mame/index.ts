import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { killSidecar as killSidecarRpc, rpc } from "../ipc";
import type { ProgressNotification } from "./types";
import type {
  BuildEvolveproInputParams,
  BuildEvolveproInputResult,
} from "@/types/mame/build_evolvepro_input";

type ProgressEventPayload = {
  kind: "kuro" | "mame";
  params: ProgressNotification;
};

let running = false;
let progressHandler: ((p: ProgressNotification) => void) | null = null;
let progressUnlisten: UnlistenFn | null = null;
let subscribePromise: Promise<void> | null = null;
/** §1 Dead-lock 감지: 마지막 progress 이벤트 수신 timestamp(ms). */
let _lastProgressAt: number | null = null;

/** 마지막 mame progress 수신 시각을 반환 (없으면 null). */
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
        if (event.payload.kind === "mame") {
          _lastProgressAt = Date.now();
          if (progressHandler) progressHandler(event.payload.params);
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
  await rpc("mame", "ping", {});
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
  const request = rpc<T>("mame", method, params, timeoutMs);
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

/**
 * Build an EVOLVEpro input xlsx from the four MAME round files (plate layout,
 * GC data, Agilent rep-batch report, previous EVOLVEpro file).
 *
 * Mirrors the ``mame.activity.build_evolvepro_input`` RPC handler. Uses a
 * longer timeout than the default because it reads four xlsx files and writes
 * two output artifacts (xlsx + JSON audit).
 */
export async function buildEvolveproInput(
  params: BuildEvolveproInputParams,
): Promise<BuildEvolveproInputResult> {
  return sendRequest<BuildEvolveproInputResult>(
    "mame.activity.build_evolvepro_input",
    params as unknown as Record<string, unknown>,
    120_000,
  );
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
