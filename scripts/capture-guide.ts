/**
 * KURO guide screenshot capture script.
 *
 * Usage: pnpm run capture-guide      (Windows side; see AGENTS.md for WSL rules)
 *
 * Starts a Vite dev server with MOCK_MODE=1, then drives a Playwright browser
 * through each screen state defined in mock-data.ts and writes
 * docs/screenshots/XX-name.png.
 *
 * Design notes (2026-08-18 rewrite):
 * - The app boots into onboarding because the Tauri bridge is absent, so every
 *   screen first dispatches `kuma:project-load-request`, the same event the
 *   Home screen uses, to reach the workspace shell (App.tsx registers the
 *   listener regardless of the current screen).
 * - The KURO workspace is a step wizard, so each screen declares `nav`
 *   (a navigationSlice sub-step) alongside its store state.
 * - Every wait is bounded. A failing screen is recorded and the run continues;
 *   the failure list is printed at the end and sets a non-zero exit code.
 * - Progress is appended to a log file because PowerShell buffers stdout until
 *   the process exits.
 */

import { chromium, type Browser, type Page } from "playwright";
import { spawn, type ChildProcess } from "child_process";
import { resolve, dirname, join } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync, appendFileSync } from "fs";
import { screenStates } from "./mock-data.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SCREENSHOTS_DIR = resolve(ROOT, "docs", "screenshots");
const PORT = Number(process.env.CAPTURE_PORT ?? 1421);
const BASE_URL = `http://localhost:${PORT}`;
const LOG_PATH = process.env.CAPTURE_LOG || resolve(ROOT, ".capture", "capture.log");

// Per-screen budget. A screen that blows it is recorded as failed and skipped.
const SCREEN_TIMEOUT_MS = Number(process.env.CAPTURE_SCREEN_TIMEOUT ?? 60_000);
const STORE_TIMEOUT_MS = 20_000;
const WORKSPACE_TIMEOUT_MS = 20_000;

mkdirSync(dirname(LOG_PATH), { recursive: true });

function log(msg: string): void {
  const line = `[${new Date().toISOString()}] ${msg}`;
  try {
    appendFileSync(LOG_PATH, line + "\n");
  } catch {
    /* logging must never break a run */
  }
  console.log(line);
}

function buildEnv(): NodeJS.ProcessEnv {
  const existing = process.env.LD_LIBRARY_PATH ?? "";
  const home = process.env.HOME ?? "";
  const condaLibPaths = [
    home ? join(home, "miniforge3", "lib") : "",
    home ? join(home, "anaconda3", "lib") : "",
    join("/opt", "conda", "lib"),
  ].filter((p) => p && existsSync(p));
  const ldPath = [...condaLibPaths, existing].filter(Boolean).join(":");
  return { ...process.env, LD_LIBRARY_PATH: ldPath || undefined };
}

function ensureDir(dir: string) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

async function serverAnswers(): Promise<boolean> {
  try {
    const res = await fetch(BASE_URL);
    return res.status < 500;
  } catch {
    return false;
  }
}

/** Bounded polling. The timeout check runs on every tick, not only on error. */
async function waitForServer(timeoutMs = 60_000): Promise<void> {
  const start = Date.now();
  for (;;) {
    if (await serverAnswers()) return;
    if (Date.now() - start > timeoutMs) {
      throw new Error(`Server at ${BASE_URL} did not start within ${timeoutMs}ms`);
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

/**
 * Spawn Vite through node directly (no shell). A shell wrapper leaves the real
 * vite process orphaned on kill, and the orphan then holds the port so the next
 * run silently attaches to a stale server.
 */
async function startViteServer(): Promise<ChildProcess> {
  if (await serverAnswers()) {
    throw new Error(
      `Port ${PORT} is already serving. Stop that process first: this run must own its dev server ` +
        `(attaching to a foreign server can capture stale code).`,
    );
  }

  log("Starting Vite dev server (MOCK_MODE=1) ...");
  const viteBin = resolve(ROOT, "node_modules", "vite", "bin", "vite.js");
  if (!existsSync(viteBin)) {
    throw new Error(`vite not found at ${viteBin} (run install in this checkout)`);
  }

  const child = spawn(process.execPath, [viteBin, "--port", String(PORT), "--strictPort"], {
    cwd: ROOT,
    env: { ...buildEnv(), MOCK_MODE: "1" },
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout?.on("data", (d: Buffer) => {
    const line = d.toString().trim();
    if (line) log(`  [vite] ${line}`);
  });
  child.stderr?.on("data", (d: Buffer) => {
    const line = d.toString().trim();
    if (line) log(`  [vite:err] ${line}`);
  });

  await waitForServer();
  log("Vite server ready.");
  return child;
}

function withTimeout<T>(label: string, p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((res, rej) => {
    const timer = setTimeout(() => rej(new Error(`${label} timed out after ${ms}ms`)), ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        res(v);
      },
      (e) => {
        clearTimeout(timer);
        rej(e);
      },
    );
  });
}

/** Boot the page into the KURO workspace shell. */
async function enterWorkspace(page: Page): Promise<void> {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

  await page.waitForFunction(
    () => typeof (window as unknown as Record<string, unknown>).__store !== "undefined",
    { timeout: STORE_TIMEOUT_MS },
  );

  // Same event the Home screen fires. loadProject() rejects without the Tauri
  // bridge, and App.tsx falls back to a name-only project and shows MainShell.
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent("kuma:project-load-request", { detail: { path: "C:\\samples\\kuro-demo" } }),
    );
  });

  // Workspace marker: the shell renders the app bar + menu bar + workflow rail,
  // far more buttons than onboarding (2) or home. Language independent.
  await page.waitForFunction(() => document.querySelectorAll("button").length > 10, {
    timeout: WORKSPACE_TIMEOUT_MS,
  });
  await page.waitForTimeout(400);
}

/**
 * Minimal Tauri bridge, injected as source text.
 *
 * Without it every sidecar call short-circuits with "Tauri bridge unavailable":
 * the polymerase dropdown stays on its loading placeholder, the error is
 * painted into the status bar of every shot, and the custom polymerase editor
 * cannot open at all (it only opens after get_polymerase_details answers).
 *
 * Passed as a string rather than a function on purpose. tsx compiles this file
 * with esbuild keepNames, which wraps nested functions in a `__name(...)`
 * helper; Playwright serialises the function body alone, so the helper is
 * undefined in the page and the whole init script dies with a ReferenceError.
 * A string is injected verbatim and cannot pick up build helpers.
 */
const TAURI_STUB_SOURCE = `
(() => {
  const profile = {
    name: "KOD", tm_method: "santalucia", salt_correction: "santalucia",
    opt_tm: 68, min_tm: 63, max_tm: 73, min_gc: 40, max_gc: 60,
    salt_monovalent: 50, salt_divalent: 1.5, dntp_conc: 0.8, dna_conc: 250,
    opt_tm_fwd: 62, opt_tm_rev: 58, opt_tm_overlap: 42, default_overlap_mode: null,
  };
  const list = ["Taq", "Phusion", "Q5", "KOD", "DreamTaq", "TAKARA_GXL", "Q5 SDM"]
    .map((name) => ({ name, manufacturer: "", fidelity: "" }));
  const rpc = {
    // useSidecar reads a failed ping as a dead sidecar and shows a retry
    // banner, so this one decides whether the workspace looks healthy.
    ping: { ok: true },
    list_polymerases: list,
    get_polymerase_details: profile,
    list_organisms: [{ key: "ecoli", name: "E. coli K-12", taxid: 83333 }],
    // The export step previews the Echo worklist as soon as it renders.
    export_echo_mapping_dry_run: {
      rows: [
        { source_plate: "Source[1]", source_well_name: "N267F_F", source_well: "A01", dest_plate: "Destination[1]", dest_well_name: "N267F", dest_well: "A01", transfer_vol: 500, mutation: "N267F" },
        { source_plate: "Source[1]", source_well_name: "Q163W_F", source_well: "B01", dest_plate: "Destination[1]", dest_well_name: "Q163W", dest_well: "B01", transfer_vol: 500, mutation: "Q163W" },
        { source_plate: "Source[1]", source_well_name: "G28I_F", source_well: "C01", dest_plate: "Destination[1]", dest_well_name: "G28I", dest_well: "C01", transfer_vol: 500, mutation: "G28I" },
      ],
      total: 91,
      transfer_vol: 500,
    },
    export_janus_mapping_dry_run: {
      rows: [
        { name: "N267F_F", type: "primer", no: 1, asp_rack: "fw plate", asp_posi: "A01", dsp_rack: "PCR mixture plate", dsp_posi: "A01", volume: 2, mutation: "N267F", role: "fwd" },
        { name: "N267F_R", type: "primer", no: 2, asp_rack: "rv plate", asp_posi: "A01", dsp_rack: "PCR mixture plate", dsp_posi: "A01", volume: 2, mutation: "N267F", role: "rev" },
        { name: "Q163W_F", type: "primer", no: 3, asp_rack: "fw plate", asp_posi: "B01", dsp_rack: "PCR mixture plate", dsp_posi: "B01", volume: 2, mutation: "Q163W", role: "fwd" },
      ],
      total: 182,
      transfer_vol: 2,
    },
  };
  window.__TAURI_INTERNALS__ = {
    invoke: async (cmd, args) => {
      if (cmd === "sidecar_rpc") {
        const method = String((args && args.method) || "");
        if (method in rpc) return rpc[method];
        throw new Error("capture stub: rpc " + method + " not stubbed");
      }
      if (cmd === "sidecar_is_running") return true;
      if (cmd === "sidecar_kill") return null;
      if (cmd === "get_config_cmd") return { projects_root: "C:\\\\samples", recent_projects: [] };
      if (cmd === "load_project_cmd") return { name: "kuro-demo" };
      if (String(cmd).indexOf("plugin:event|") === 0) return 1;
      // With the bridge present the fs plugin no longer routes through the
      // MOCK_MODE alias, so answer it here: a missing autosave file is the
      // quiet path, an unstubbed one paints a red banner across every shot.
      // Autosave resolves a directory before touching fs; an unstubbed path
      // command surfaces as the same banner.
      if (String(cmd).indexOf("plugin:path|") === 0) return "C:\\\\samples\\\\kuro-demo";
      if (String(cmd).indexOf("plugin:fs|") === 0) {
        return String(cmd).indexOf("exists") >= 0 ? false : null;
      }
      throw new Error("capture stub: command " + cmd + " not stubbed");
    },
    transformCallback: (cb) => {
      const id = Math.floor(Math.random() * 1e9);
      window["_" + id] = cb;
      return id;
    },
  };
})();
`;

// Panel layout keys the app reads once at mount. Reset every screen so a
// screen-specific override does not leak into the next one.
const STORAGE_DEFAULTS: Record<string, string> = {
  "kuro.output.split": "50",
  "kuro.output.plateCollapsed": "0",
};

async function captureScreen(page: Page, screen: (typeof screenStates)[number]): Promise<void> {
  // Written on a throwaway visit: the app reads these during the next mount.
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await page.evaluate((kv: Record<string, string>) => {
    for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, v);
  }, { ...STORAGE_DEFAULTS, ...(screen.storage ?? {}) });

  await enterWorkspace(page);

  await page.evaluate((state: Record<string, unknown>) => {
    const store = (window as unknown as Record<string, unknown>).__store as {
      setState: (s: Record<string, unknown>) => void;
    };
    store.setState(state);
  }, screen.state);

  if (screen.nav) {
    await page.evaluate((sub: string) => {
      const store = (window as unknown as Record<string, unknown>).__store as {
        getState: () => { setSubStep: (id: string) => void };
      };
      store.getState().setSubStep(sub);
    }, screen.nav);
  }

  await page.waitForTimeout(screen.settleMs ?? 900);

  if (screen.click) {
    // Real pointer events. Radix menus and popovers open on pointerdown and
    // ignore a synthetic element.click() from page.evaluate.
    await page.locator(screen.click).first().click({ timeout: 10_000 });
    await page.waitForTimeout(screen.actionSettleMs ?? 900);
  }

  if (screen.action) {
    // Wrap in an IIFE so multi-statement action bodies evaluate as expressions.
    const result = await page.evaluate(`(() => { try { ${screen.action}
      return "ok"; } catch (e) { return "action-error: " + String(e); } })()`);
    if (typeof result === "string" && result !== "ok") {
      throw new Error(String(result));
    }
    await page.waitForTimeout(screen.actionSettleMs ?? 900);
  }

  // Toasts are transient chrome (autosave warnings caused by the missing Tauri
  // bridge) and would otherwise cover the top-right of every shot.
  await page.evaluate(() => {
    document.querySelectorAll("[data-sonner-toaster]").forEach((n) => n.remove());
  });
  await page.waitForTimeout(150);

  const outPath = resolve(SCREENSHOTS_DIR, `${screen.name}.png`);
  await page.screenshot({ path: outPath, fullPage: false });
}

async function main() {
  ensureDir(SCREENSHOTS_DIR);
  log(`=== capture run start (${screenStates.length} screens) ===`);

  const env = buildEnv();
  if (env.LD_LIBRARY_PATH) process.env.LD_LIBRARY_PATH = env.LD_LIBRARY_PATH;

  const vite = await startViteServer();
  const failures: { name: string; reason: string }[] = [];
  let browser: Browser | undefined;

  try {
    browser = await chromium.launch({
      channel:
        process.env.CAPTURE_CHANNEL || (process.platform === "win32" ? "msedge" : undefined),
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    });

    const context = await browser.newContext({
      viewport: { width: 1400, height: 900 },
      deviceScaleFactor: 2,
    });

    // English UI (guide docs are English) and no first-run toasts.
    await context.addInitScript(() => {
      try {
        localStorage.setItem("kuma:locale", "en");
        localStorage.setItem("kuma.onboarding.maximizeShown", "1");
        localStorage.setItem("kuma:autosave-intro-shown", "1");
      } catch {
        /* ignore */
      }
    });

    // Minimal Tauri bridge. Without it every sidecar call short-circuits with
    // "Tauri bridge unavailable", which leaves the polymerase dropdown empty,
    // paints the error into the status bar of every shot, and makes the custom
    // polymerase editor impossible to open (it only opens after
    // get_polymerase_details answers). Unstubbed commands reject, which is the
    // same failure shape the app already handles.
    await context.addInitScript({ content: TAURI_STUB_SOURCE });

    const page = await context.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") log(`  [browser:error] ${msg.text()}`);
    });

    let bridgeLogged = false;
    for (const screen of screenStates) {
      log(`Capturing: ${screen.name}`);
      if (!bridgeLogged) {
        bridgeLogged = true;
        await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
        const kind = await page.evaluate(
          () => typeof (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__,
        );
        log(`  bridge stub: ${kind}`);
      }
      try {
        await withTimeout(screen.name, captureScreen(page, screen), SCREEN_TIMEOUT_MS);
        log(`  -> saved: docs/screenshots/${screen.name}.png`);
      } catch (err) {
        const reason = err instanceof Error ? err.message : String(err);
        failures.push({ name: screen.name, reason });
        log(`  !! FAILED ${screen.name}: ${reason}`);
      }
    }

    await context.close();
  } finally {
    if (browser) await browser.close();
    vite.kill();
    log("Vite server stopped.");
  }

  const ok = screenStates.length - failures.length;
  log(`Done. ${ok}/${screenStates.length} screenshots saved to docs/screenshots/`);
  if (failures.length) {
    log(`Failed screens (${failures.length}):`);
    for (const f of failures) log(`  - ${f.name}: ${f.reason}`);
    process.exitCode = 1;
  }
}

main().catch((err) => {
  log(`Fatal error: ${err instanceof Error ? err.stack : String(err)}`);
  process.exit(1);
});
