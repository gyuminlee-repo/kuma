// ui-smoke-server.mjs
//
// Start the preview server for scripts/ui-smoke.mjs and prove the page it then
// tests is served by that process. Readiness used to be "anything on the port
// answers 200", so an older preview from another checkout could hold the port,
// the new one exit on --strictPort, and the smoke pass against the old page.
//
// Two rules close that: the port must be silent before the spawn, and the
// child must still be running when the port first answers. A child exit or
// spawn error before readiness rejects at once instead of waiting out the
// timeout.

import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

async function answers(url) {
  try {
    const response = await fetch(url);
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Spawn `command args` and resolve with the child once `url` answers while
 * that child is alive. Rejects if `url` already answers before the spawn, if
 * the child errors or exits first, or on timeout (the child is killed then).
 */
export async function startOwnedServer({ command, args, url, spawnOptions = {}, timeoutMs = 30000 }) {
  if (await answers(url)) {
    throw new Error(
      `${url} is already served by another process; stop it so the smoke tests this checkout`,
    );
  }

  const child = spawn(command, args, spawnOptions);
  let exited = null;
  const failure = new Promise((_, reject) => {
    child.once("error", (err) => {
      exited = err;
      reject(new Error(`preview server failed to start: ${err.message}`));
    });
    child.once("exit", (code, signal) => {
      exited = { code, signal };
      reject(new Error(`preview server exited before it was ready (code ${code}, signal ${signal})`));
    });
  });
  failure.catch(() => {});

  const ready = (async () => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (exited || (await answers(url))) return;
      await delay(250);
    }
    throw new Error(`Timed out waiting for preview server at ${url}`);
  })();

  try {
    await Promise.race([ready, failure]);
    if (exited) await failure;
  } catch (err) {
    if (!exited) child.kill("SIGKILL");
    throw err;
  }
  return child;
}

/** Throw if the server child has exited since it became ready. */
export function assertStillRunning(child) {
  if (child.exitCode !== null || child.signalCode !== null) {
    throw new Error(
      `preview server exited during the smoke (code ${child.exitCode}, signal ${child.signalCode})`,
    );
  }
}
