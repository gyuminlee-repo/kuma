import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileSync, unlinkSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { chromium } from "playwright";
import { computeFingerprint } from "./ui-smoke-fingerprint.mjs";

const HOST = "127.0.0.1";
const PORT = 4173;
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");
const MARKER_PATH = resolve(REPO_ROOT, ".ui-smoke-passed");
const VITE_BIN = resolve(
  REPO_ROOT,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "vite.cmd" : "vite",
);
// Called directly through `node`, never through a package manager or an
// on-demand runner (npx/pnpm dlx): this checkout is a WSL-shared folder and
// this script must stay self-contained (see AGENTS.md "Git hooks").
const VITE_JS = resolve(REPO_ROOT, "node_modules", "vite", "bin", "vite.js");
const URL = `http://${HOST}:${PORT}`;

async function waitForServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Server not ready yet.
    }
    await delay(500);
  }
  throw new Error(`Timed out waiting for preview server at ${url}`);
}

/**
 * Waits for a spawned child process to actually exit, escalating from SIGTERM
 * to SIGKILL after a grace period.
 *
 * The previous version called `server.kill("SIGTERM")` and then checked
 * `server.killed`, which Node sets to true the instant the signal is *sent*,
 * not when the process actually dies, so `if (!server.killed)` could never
 * be true and the SIGKILL branch was dead code (AUDIT K-11). A preview
 * server that ignores SIGTERM stayed alive and held the port, breaking the
 * next `--strictPort` run.
 */
function killAndWait(child, { graceMs = 2000 } = {}) {
  return new Promise((resolveKill) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolveKill();
      return;
    }
    let settled = false;
    const onExit = () => {
      if (settled) return;
      settled = true;
      clearTimeout(escalate);
      resolveKill();
    };
    child.once("exit", onExit);
    const escalate = setTimeout(() => {
      if (settled) return;
      child.kill("SIGKILL");
    }, graceMs);
    child.kill("SIGTERM");
  });
}

/**
 * Runs `node <scriptPath> ...args` to completion, inheriting stdio so build
 * output/errors are visible, and rejects on a non-zero exit or a signal kill.
 */
function runNodeScript(scriptPath, args, { cwd = REPO_ROOT } = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, [scriptPath, ...args], {
      cwd,
      stdio: "inherit",
    });
    child.on("error", rejectRun);
    child.on("exit", (code, signal) => {
      if (signal) {
        rejectRun(new Error(`${scriptPath} ${args.join(" ")} killed by signal ${signal}`));
      } else if (code !== 0) {
        rejectRun(new Error(`${scriptPath} ${args.join(" ")} exited with code ${code}`));
      } else {
        resolveRun();
      }
    });
  });
}

/**
 * Builds the production bundle this script is about to smoke-test.
 *
 * Without this, `ui-smoke.mjs` served whatever `dist/` happened to already
 * be on disk. A stale `dist/` from a prior, unrelated build let a genuinely
 * broken checkout pass: reproduced by injecting a `throw` at the top of
 * `MameTab.tsx` and running the smoke script without rebuilding first, it
 * exited 0 and recorded a marker for the broken source. Building here makes
 * the script self-contained: whatever it certifies is what it just compiled.
 */
async function buildFrontend() {
  const t0 = Date.now();
  await runNodeScript(VITE_JS, ["build"]);
  const elapsedS = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`ui-smoke: build finished in ${elapsedS}s`);
}

/**
 * Minimal `window.__TAURI_INTERNALS__` bridge, injected before any app script
 * runs. Without it `App.tsx`'s `getConfig()` call rejects (no Tauri backend
 * behind `vite preview`) and the app is permanently stuck on the onboarding
 * screen, so the smoke test could never reach MainShell, let alone the
 * KURO/MAME tabs it exists to check.
 *
 * This runs inside the real production bundle (`vite build` with no special
 * mode), unlike the MOCK_MODE build used for screenshot capture: MOCK_MODE
 * aliases several modules at build time and needs generated, gitignored
 * fixture files (scripts/real-data.json, scripts/mame-real-data.json) that
 * are not guaranteed to exist. Stubbing only the Tauri IPC bridge at the
 * Playwright layer needs neither and exercises the exact bundle that ships.
 *
 * The command set below is the minimum observed (empirically, by watching
 * for "no stub" console errors while driving the real production build) to
 * reach: Home -> open recent project -> MainShell -> KURO tab default view
 * -> MAME tab default view, with zero pageerrors. It intentionally does not
 * attempt to support deeper wizard steps (file uploads, sidecar RPC
 * payloads); that is screenshot-capture territory (scripts/capture-*.ts),
 * not this smoke gate's job.
 *
 * Any command outside this set is recorded on `window.__uiSmokeMissingCommands`
 * (checked by the driver after the run) instead of failing silently. A
 * console.error line is also emitted for a human reading the transcript, but
 * nothing here relies on that being read: the page-global array is what the
 * driver actually inspects.
 */
function installTauriBridgeStub() {
  window.__uiSmokeMissingCommands = [];
  const CONFIG = {
    projects_root: "~/Documents/kuma",
    recent_projects: [
      {
        path: "~/Documents/kuma/ui-smoke-project",
        name: "ui-smoke-project",
        last_opened: "2026-01-01T00:00:00Z",
        project_id: "00000000-0000-4000-8000-000000000000",
      },
    ],
  };
  let callbackId = 0;
  function transformCallback() {
    callbackId += 1;
    return callbackId;
  }
  const missing = new Set();
  function invoke(cmd, args) {
    args = args || {};
    switch (cmd) {
      case "get_config_cmd":
        return Promise.resolve(CONFIG);
      case "list_recent_projects_cmd":
        return Promise.resolve(CONFIG.recent_projects);
      case "list_restorable_projects_cmd":
        return Promise.resolve([]);
      case "remove_recent_project_cmd":
        return Promise.resolve(CONFIG.recent_projects);
      case "load_project_cmd":
        return Promise.resolve({
          schema: 1,
          project_id: CONFIG.recent_projects[0].project_id,
          name: CONFIG.recent_projects[0].name,
          stage: "draft",
        });
      case "create_project_cmd":
        return Promise.resolve(CONFIG.recent_projects[0].path);
      case "sidecar_is_running":
        return Promise.resolve(true);
      case "sidecar_kill":
        return Promise.resolve(null);
      case "sidecar_rpc":
        return Promise.resolve({});
      case "probe_writable_dir":
        return Promise.resolve(true);
      case "read_text_head":
        return Promise.resolve("");
      case "keep_awake_start":
        return Promise.resolve(null);
      case "keep_awake_stop":
        return Promise.resolve(null);
      case "plugin:path|is_absolute":
        return Promise.resolve(String(args.path || "").startsWith("/"));
      case "plugin:path|join":
        return Promise.resolve((args.paths || []).filter(Boolean).join("/"));
      case "plugin:path|resolve":
        return Promise.resolve((args.paths || []).filter(Boolean).join("/"));
      case "plugin:path|resolve_directory":
        return Promise.resolve(CONFIG.recent_projects[0].path);
      case "plugin:path|basename": {
        const raw = String(args.path || "");
        return Promise.resolve(raw.slice(raw.lastIndexOf("/") + 1));
      }
      case "plugin:path|dirname": {
        const raw = String(args.path || "");
        return Promise.resolve(raw.slice(0, Math.max(raw.lastIndexOf("/"), 0)));
      }
      case "plugin:path|normalize":
        return Promise.resolve(String(args.path || ""));
      case "plugin:path|extname":
        return Promise.resolve("");
      case "plugin:event|listen":
        return Promise.resolve(++callbackId);
      case "plugin:event|unlisten":
        return Promise.resolve(null);
      case "plugin:event|emit":
        return Promise.resolve(null);
      case "plugin:event|emit_to":
        return Promise.resolve(null);
      case "plugin:fs|exists":
        return Promise.resolve(false);
      case "plugin:fs|mkdir":
        return Promise.resolve(null);
      case "plugin:fs|read_text_file":
        return Promise.reject(new Error("ENOENT (ui-smoke stub)"));
      case "plugin:fs|write_text_file":
        return Promise.resolve(null);
      case "plugin:fs|rename":
        return Promise.resolve(null);
      case "plugin:fs|remove":
        return Promise.resolve(null);
      case "plugin:fs|stat":
        return Promise.reject(new Error("ENOENT (ui-smoke stub)"));
      case "plugin:fs|read_dir":
        return Promise.resolve([]);
      case "plugin:window|set_title":
        return Promise.resolve(null);
      default:
        if (!missing.has(cmd)) {
          missing.add(cmd);
          console.error(`ui-smoke: no stub for Tauri command "${cmd}"`);
          window.__uiSmokeMissingCommands.push(cmd);
        }
        return Promise.resolve(null);
    }
  }
  window.__TAURI_INTERNALS__ = {
    invoke,
    transformCallback,
    unregisterCallback: function () {},
    convertFileSrc: function (p) {
      return p;
    },
    metadata: {
      currentWindow: { label: "main" },
      currentWebview: { windowLabel: "main", label: "main" },
    },
  };
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: function () {} };
  window.isTauri = true;
}

function currentCommitSha() {
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    }).trim();
  } catch {
    return null;
  }
}

function writeMarker(fingerprint) {
  const marker = {
    fingerprint,
    ts: new Date().toISOString(),
    commit: currentCommitSha(),
  };
  writeFileSync(MARKER_PATH, JSON.stringify(marker) + "\n", "utf8");
  return marker;
}

function clearMarker() {
  if (existsSync(MARKER_PATH)) {
    unlinkSync(MARKER_PATH);
  }
}

/**
 * Runs the Chromium checks against an already-running preview server.
 * Returns once every assertion (title, root render, KURO tab, MAME tab, zero
 * pageerrors, zero unstubbed Tauri commands) has passed; throws otherwise.
 */
async function runBrowserChecks() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    // Runs before any app script on every navigation in this context, so the
    // bridge exists the instant App.tsx's first effect calls getConfig().
    await context.addInitScript(installTauriBridgeStub);
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => {
      pageErrors.push(error);
    });

    await page.goto(URL, { waitUntil: "networkidle" });
    await page.waitForLoadState("domcontentloaded");

    const title = await page.title();
    if (title !== "kuma") {
      throw new Error(`Unexpected page title: ${title}`);
    }
    const rootHtml = await page.locator("#root").evaluate((el) => el.innerHTML.trim());
    if (!rootHtml) {
      throw new Error("App root did not render any content");
    }

    // Home -> open the stubbed recent project -> MainShell. Text-filtered
    // button rather than a role/name lookup: the card has no accessible name
    // beyond its own text content (see src/screens/Home.tsx), and that text
    // is the one value in this stub under our control end to end.
    const projectCard = page
      .locator("button")
      .filter({ hasText: "ui-smoke-project" })
      .first();
    await projectCard.waitFor({ state: "visible", timeout: 15000 });
    await projectCard.click();

    // Tab labels ("Kuro"/"Mame") come from GlobalAppBar's static TABS table,
    // not from an i18n key, so unlike most on-screen text they are stable
    // across locales and safe to select on by role+name.
    const kuroTab = page.getByRole("tab", { name: "Kuro" });
    await kuroTab.waitFor({ state: "visible", timeout: 15000 });
    await kuroTab.click();
    // Proof that the KURO lazy chunk actually loaded and rendered, not just
    // that the tab button exists: a heading inside the active tabpanel.
    const kuroHeading = page
      .locator('[role="tabpanel"] h1, [role="tabpanel"] h2, [role="tabpanel"] h3')
      .first();
    await kuroHeading.waitFor({ state: "visible", timeout: 20000 });
    if (pageErrors.length > 0) {
      throw pageErrors[0];
    }

    const mameTab = page.getByRole("tab", { name: "Mame" });
    await mameTab.waitFor({ state: "visible", timeout: 15000 });
    await mameTab.click();
    const mameHeading = page
      .locator('[role="tabpanel"] h1, [role="tabpanel"] h2, [role="tabpanel"] h3')
      .first();
    await mameHeading.waitFor({ state: "visible", timeout: 20000 });
    if (pageErrors.length > 0) {
      throw pageErrors[0];
    }

    // An app code path calling a Tauri command outside the stub's known set
    // must fail the gate, not resolve to `null` and render "successfully"
    // with data it never actually asked for.
    const missingCommands = await page.evaluate(() => window.__uiSmokeMissingCommands || []);
    if (missingCommands.length > 0) {
      throw new Error(
        `ui-smoke: unstubbed Tauri command(s) called: ${missingCommands.join(", ")}`,
      );
    }
  } finally {
    await browser.close();
  }
}

// ─── main ───────────────────────────────────────────────────────────────

let passed = false;
let failure = null;
let preFingerprint = null;

// One place to track "whatever child process is currently our responsibility
// to clean up", so the SIGINT/SIGTERM handler below has something to kill
// regardless of which phase (build or preview) is running when the signal
// arrives.
let activeChild = null;
let shuttingDownFromSignal = false;

async function handleSignal(signal) {
  if (shuttingDownFromSignal) return;
  shuttingDownFromSignal = true;
  console.error(`\nui-smoke: received ${signal}, cleaning up`);
  clearMarker();
  if (activeChild) {
    await killAndWait(activeChild);
  }
  process.exit(signal === "SIGINT" ? 130 : 143);
}
process.on("SIGINT", () => void handleSignal("SIGINT"));
process.on("SIGTERM", () => void handleSignal("SIGTERM"));

try {
  // Fingerprint the source tree right before it is compiled: this is the
  // exact state the upcoming build (and therefore everything the browser
  // checks below observe) reflects. Recomputed again at the end; if it
  // differs, some other lane edited src/ mid-run and the pass below does not
  // certify the code currently on disk (AGENTS.md documents parallel lanes
  // as the normal case here, not an edge case).
  preFingerprint = computeFingerprint(REPO_ROOT);

  await buildFrontend();

  const server = spawn(
    VITE_BIN,
    ["preview", "--host", HOST, "--port", String(PORT), "--strictPort"],
    {
      stdio: "inherit",
      shell: process.platform === "win32",
    },
  );
  activeChild = server;

  const checksStart = Date.now();
  try {
    await waitForServer(URL);
    await runBrowserChecks();
  } finally {
    await killAndWait(server);
    activeChild = null;
  }
  const checksElapsedS = ((Date.now() - checksStart) / 1000).toFixed(1);
  console.log(`ui-smoke: browser checks finished in ${checksElapsedS}s`);

  const postFingerprint = computeFingerprint(REPO_ROOT);
  if (postFingerprint !== preFingerprint) {
    throw new Error(
      "ui-smoke: source tree changed while the smoke test was running " +
        `(fingerprint ${preFingerprint} -> ${postFingerprint}); ` +
        "cannot certify code that no longer matches what was built. Re-run.",
    );
  }

  passed = true;
} catch (err) {
  failure = err;
}

if (passed) {
  const marker = writeMarker(preFingerprint);
  console.log(`ui-smoke: PASS (fingerprint ${marker.fingerprint})`);
} else {
  clearMarker();
  console.error("ui-smoke: FAIL");
  console.error(failure);
  process.exitCode = 1;
}
