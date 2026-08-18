import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { killSidecar as killSidecarRpc, rawSidecarRpc } from "../ipc";
import type { ProgressNotification } from "./types";
import type {
  BuildEvolveproInputParams,
  BuildEvolveproInputResult,
} from "@/types/mame/build_evolvepro_input";
import type {
  ClassifyRoundResult,
  RoundFileEntry,
} from "@/types/mame/strategy";
import { getMameRpcResultValidator } from "@/types/mame/validators";

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
  await rawSidecarRpc("mame", "ping", {});
}

/**
 * Lazy-start probe for the mame sidecar.
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
  await rawSidecarRpc("mame", "ping", {});
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

/**
 * Send one MAME JSON-RPC request and refuse a result that does not match.
 *
 * The shape check is done here rather than by each caller, mirroring
 * `src/lib/ipc-kuro/index.ts`: this is the function that hands a payload back as
 * a `T`, so it is the one that has to earn the cast. `getMameRpcResultValidator`
 * returns `null` for a method the table does not cover yet, and those go through
 * as before; `MAME_UNVALIDATED_METHODS` in `src/types/mame/validators.ts` is the
 * written-down list of which those are.
 */
export async function sendRequest<T>(
  method: string,
  params: Record<string, unknown> = {},
  timeoutMs = 60_000,
): Promise<T> {
  const validateResult = getMameRpcResultValidator(method);
  const request = rawSidecarRpc<unknown>("mame", method, params, timeoutMs);
  const timeout = new Promise<never>((_, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`RPC timeout: ${method} after ${timeoutMs}ms`));
    }, timeoutMs);
    // The catch keeps the derived promise handled. Without it a rejecting request
    // raises an unhandled rejection on top of the error the caller already gets,
    // once per failed RPC. The rejection itself still reaches the caller below.
    void request.finally(() => clearTimeout(timer)).catch(() => {});
  });

  const result = await Promise.race([request, timeout]);
  // The sidecar answered, so it is running whatever the payload turned out to
  // be. `isSidecarRunning()` gates the reset in `src/store/mame/resetAll.ts`,
  // and setting this after the shape check would skip a reset the app owes
  // because the answer was malformed.
  running = true;
  if (validateResult && !validateResult(result)) {
    // Plain message, like the timeout above: this module carries no i18next
    // dependency and a refused payload is a sidecar-contract fault an operator
    // reports rather than acts on.
    throw new Error(`Invalid RPC result shape: ${method}`);
  }
  return result as T;
}

/**
 * Advisory `classify()` call with per-round xlsx file references.
 *
 * @param roundFiles - Ordered list of {n, path, wt_values?} xlsx file entries.
 *   n is 1-based round number; the handler sorts by n internally. wt_values are
 *   the wild-type replicates step 4.1 recorded for that round, which the file
 *   itself cannot carry; only the highest-numbered entry is read.
 * @param cNext - Optional capacity of the next combinatorial plate (wells).
 *   Used to derive K_throughput = floor((1+sqrt(1+8*cNext))/2). Defaults to 96.
 * @returns ClassifyDecisionResult when the classifier answered, or
 *   ClassifyNotAssessableResult when the bootstrap gate was reached with too
 *   few wild-type replicates to run on, so the question could not be put to it.
 *   Discriminate on `advisory`.
 *   Throws a JSON-RPC error (-32602 / -32002) on bad input or missing/malformed
 *   files, and an invalid-shape error on a payload that is neither shape.
 *
 * Read-only, no confirmation button, no PI decision persistence. It lives here
 * rather than in `src/lib/ipc.ts` because that module is the raw transport both
 * sidecars share: a MAME call placed there reached the sidecar without passing
 * the MAME client, so it was cast to its result type with nothing checking it.
 */
export async function classifyRound(
  roundFiles: RoundFileEntry[],
  cNext?: number,
): Promise<ClassifyRoundResult> {
  // The call through `rpc` carried no client-side timeout at all. Reading
  // several xlsx files and running a 1000-sample bootstrap is closer to
  // `buildEvolveproInput` than to a stat-only call, so it gets the same 120 s
  // rather than the 60 s default, which would be a new way to fail.
  return sendRequest<ClassifyRoundResult>(
    "strategy.classify_round",
    {
      round_files: roundFiles,
      ...(cNext !== undefined && { c_next: cNext }),
    },
    120_000,
  );
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
