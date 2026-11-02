// ui-smoke-server.mjs
//
// Start the preview server for scripts/ui-smoke.mjs and prove the page it then
// tests is served by that process. Readiness used to be "anything on the port
// answers 200", so an older preview from another checkout could hold the port,
// the new one exit on --strictPort, and the smoke pass against the old page.
//
// Two rules close that: the port must not accept connections before the spawn
// (a listener that accepts and never answers counts as taken, not as free), and
// the child must still be running when the port first answers. A child exit or
// spawn error before readiness rejects at once instead of waiting out the
// timeout.
//
// One deadline covers the whole start, preflight included, and every probe is
// cut off at what is left of it, so a listener that accepts and then sends
// nothing cannot hold the start past `timeoutMs`.
//
// Limit: ownership is inferred, not proven. Nothing ties the answering page to
// this child (vite preview has no simple hook for a per-run token), so a
// process that binds the port between the preflight and the child's own bind
// is not told apart while the child stays alive. --strictPort makes the child
// exit in that case, which usually surfaces as "exited before it was ready".

import { spawn } from "node:child_process";
import { connect } from "node:net";
import { setTimeout as delay } from "node:timers/promises";

/** Does `url` answer 2xx within `ms`? A stalled response counts as no. */
async function answers(url, ms) {
  if (ms <= 0) return false;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(ms) });
    return response.ok;
  } catch {
    return false;
  }
}

/** Does anything accept a TCP connection on `url`'s host and port within `ms`? */
function accepts(url, ms) {
  const { hostname, port, protocol } = new URL(url);
  const portNumber = Number(port) || (protocol === "https:" ? 443 : 80);
  return new Promise((resolve) => {
    if (ms <= 0) {
      resolve(false);
      return;
    }
    const socket = connect({ host: hostname, port: portNumber });
    const done = (value) => {
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(ms, () => done(false));
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
  });
}

function timedOut(url) {
  return new Error(`Timed out waiting for preview server at ${url}`);
}

/**
 * Spawn `command args` and resolve with the child once `url` answers while
 * that child is alive. Rejects if the port already accepts connections before
 * the spawn, if the child errors or exits first, or once `timeoutMs` has
 * passed since the call (the child is killed then).
 */
export async function startOwnedServer({ command, args, url, spawnOptions = {}, timeoutMs = 30000 }) {
  const deadline = Date.now() + timeoutMs;
  const left = () => deadline - Date.now();

  if (await accepts(url, left())) {
    throw new Error(
      `${url} is already served by another process; stop it so the smoke tests this checkout`,
    );
  }
  if (left() <= 0) throw timedOut(url);

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
    while (left() > 0) {
      if (exited || (await answers(url, left()))) return;
      const wait = Math.min(250, left());
      if (wait > 0) await delay(wait);
    }
    throw timedOut(url);
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

function hasExited(child) {
  return child.exitCode !== null || child.signalCode !== null;
}

function waitForExit(child, ms) {
  if (hasExited(child)) return Promise.resolve(true);
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.off("exit", onExit);
      resolve(false);
    }, ms);
    function onExit() {
      clearTimeout(timer);
      resolve(true);
    }
    child.once("exit", onExit);
  });
}

/**
 * Stop the server child and wait for it to be gone. SIGTERM first; if the
 * child has not exited after `graceMs`, SIGKILL. `child.killed` only says a
 * signal was delivered, so the actual `exit` event is what is awaited.
 * Resolves true once the child has exited, false if even SIGKILL left it
 * running for another `graceMs`.
 */
export async function stopServer(child, { graceMs = 5000 } = {}) {
  if (hasExited(child)) return true;
  child.kill("SIGTERM");
  if (await waitForExit(child, graceMs)) return true;
  child.kill("SIGKILL");
  return waitForExit(child, graceMs);
}
