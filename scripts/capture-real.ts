/**
 * KURO screenshot capture backed by real sidecar output.
 *
 * Differences from capture-guide.ts, which this does not replace:
 *   - screen states come from real-data.ts, so the tables show values the
 *     sidecar computed from the lab IspS records rather than a fixture
 *   - the wizard position (currentMajor / currentSubStep) is set alongside the
 *     store state, so the output and export screens are reachable at all
 *   - the run refuses to start when port 1421 is already taken, instead of
 *     silently attaching to another session's server and capturing its build
 *   - Vite is spawned without a shell, so killing it does not orphan a node
 *     grandchild that keeps the port
 *   - a screen action that matches nothing aborts the run. The 2026-04 set had
 *     two files whose names promised a dialog and whose bytes were the plain
 *     main screen, because the old harness let a missed selector pass.
 *
 * Usage:
 *   .venv/bin/python scripts/gen_real_capture_data.py
 *   pnpm exec tsx scripts/capture-real.ts [--out docs/screenshots-real]
 */

import { chromium, type Page } from "playwright";
import { spawn, execFileSync, type ChildProcess } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync, writeFileSync } from "fs";
import { screenStates, type ScreenState } from "./real-data.js";

declare global {
  interface Window {
    /** Exposed by src/main.tsx in dev builds only. */
    __store?: {
      getState: () => Record<string, unknown>;
      setState: (partial: Record<string, unknown>) => void;
    };
  }
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const PORT = 1421;
const BASE_URL = `http://localhost:${PORT}`;
const VIEWPORT = { width: 1440, height: 1120 };

function outputDir(): string {
  const flagIndex = process.argv.indexOf("--out");
  const relative = flagIndex >= 0 ? process.argv[flagIndex + 1] : "docs/screenshots-real";
  return resolve(ROOT, relative);
}

function portHolders(): string[] {
  try {
    const out = execFileSync("lsof", ["-ti", `:${PORT}`], { encoding: "utf8" });
    return out.split("\n").filter(Boolean);
  } catch {
    // lsof exits non-zero when nothing holds the port, which is the good case.
    return [];
  }
}

function waitForServer(url: string, timeoutMs = 60_000): Promise<void> {
  const start = Date.now();
  return new Promise((resolveWait, rejectWait) => {
    const tick = async () => {
      try {
        const res = await fetch(url);
        if (res.status < 500) return resolveWait();
      } catch {
        // Connection refused until Vite binds; the deadline below is the guard.
      }
      if (Date.now() - start > timeoutMs) {
        return rejectWait(new Error(`Vite did not answer on ${url} within ${timeoutMs}ms`));
      }
      setTimeout(() => void tick(), 400);
    };
    void tick();
  });
}

async function startVite(): Promise<ChildProcess> {
  const holders = portHolders();
  if (holders.length > 0) {
    throw new Error(
      `port ${PORT} is held by pid(s) ${holders.join(", ")}. ` +
        `Capturing now would attach to that server and screenshot its build. ` +
        `Stop it first (kill ${holders.join(" ")}).`,
    );
  }

  // No shell: a shell wrapper would absorb the kill and leave the real node
  // process holding the port for the next run.
  const child = spawn(
    process.execPath,
    [resolve(ROOT, "node_modules/vite/bin/vite.js"), "--port", String(PORT), "--strictPort"],
    {
      cwd: ROOT,
      env: { ...process.env, MOCK_MODE: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  child.stdout?.on("data", (data: Buffer) => {
    const line = data.toString().trim();
    if (line) console.log(`  [vite] ${line}`);
  });
  child.stderr?.on("data", (data: Buffer) => {
    const line = data.toString().trim();
    if (line) console.error(`  [vite:err] ${line}`);
  });

  await waitForServer(BASE_URL);
  return child;
}

/** Walk the project picker into the workspace using the real Home screen. */
async function enterWorkspace(page: Page): Promise<void> {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => typeof window.__store !== "undefined", { timeout: 20_000 });

  const card = page
    .locator("button, [role='button'], li, article")
    .filter({ hasText: "ispS_evolvepro_round1" })
    .first();
  await card.waitFor({ state: "visible", timeout: 20_000 });
  await card.click();

  // The workspace mounts the wizard rail; wait for it rather than a fixed sleep.
  await page.waitForFunction(
    () => Boolean(window.__store && "currentSubStep" in window.__store.getState()),
    { timeout: 20_000 },
  );
}

/**
 * The external-database consent modal is raised by any screen that touches
 * UniProt, InterPro or the benchmark. Once open it covers every later screen,
 * which is how three files came out byte-identical on the first full run. The
 * lookups are already resolved offline into real-data.json, so the capture run
 * marks consent as settled and keeps it settled between screens.
 */
async function settleConsent(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (!window.__store) return;
    window.__store.setState({ networkConsentGranted: true, networkConsentPending: false });
  });
}

/**
 * A Radix dropdown opened for one screen stays open into the next one, which is
 * how 14-polymerase-editor came out showing the File menu. Escape closes
 * whatever layer is on top before the next state lands.
 */
async function dismissOverlays(page: Page): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(120);
  }
}

async function applyState(page: Page, screen: ScreenState): Promise<void> {
  await dismissOverlays(page);
  await settleConsent(page);
  await page.evaluate(
    ({ state, nav }) => {
      if (!window.__store) throw new Error("window.__store missing; is MOCK_MODE dev build running?");
      window.__store.setState({ ...state, ...(nav ?? {}) });
    },
    { state: screen.state, nav: screen.nav ?? null },
  );
  // Dialogs behind React.lazy need a beat to fetch their chunk before the shot.
  await page.waitForTimeout(900);

  if (screen.click) {
    // Radix menus and popovers open on pointerdown, which a JS .click() inside
    // page.evaluate never dispatches. These have to go through real input.
    const target = page.locator(screen.click).first();
    await target.waitFor({ state: "visible", timeout: 10_000 });
    await target.click();
    await page.waitForTimeout(600);
  }

  if (screen.action) {
    // A miss here yields a screenshot that contradicts its own filename, so it
    // is a hard failure rather than a warning.
    const hit = await page.evaluate<boolean>(`(async () => { ${screen.action} })()`);
    if (hit === false) {
      throw new Error(`${screen.name}: action matched no element`);
    }
    await page.waitForTimeout(500);
  }
}

async function main(): Promise<void> {
  const dir = outputDir();
  if (!existsSync(resolve(ROOT, "scripts/real-data.json"))) {
    throw new Error("scripts/real-data.json missing. Run scripts/gen_real_capture_data.py first.");
  }
  mkdirSync(dir, { recursive: true });

  const vite = await startVite();
  const browser = await chromium.launch({ headless: true });
  const manifest: Array<{ name: string; caption: string; file: string }> = [];

  try {
    const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
    const page = await context.newPage();
    const gaps: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      console.warn(`  [browser:error] ${text}`);
      if (text.includes("no recorded sidecar reply")) gaps.push(text);
    });

    await enterWorkspace(page);

    for (const screen of screenStates) {
      console.log(`[capture] ${screen.name}`);
      await applyState(page, screen);
      const file = `${screen.name}.png`;
      await page.screenshot({ path: resolve(dir, file), fullPage: false });
      manifest.push({ name: screen.name, caption: screen.caption, file });
    }

    if (gaps.length > 0) {
      // A gap paints "MOCK_MODE" into the app status bar, so the set is not
      // publishable until the generator records that RPC.
      throw new Error(`unrecorded sidecar replies: ${[...new Set(gaps)].join(", ")}`);
    }

    writeFileSync(
      resolve(dir, "captions.json"),
      JSON.stringify(manifest, null, 2) + "\n",
      "utf8",
    );
    await context.close();
    console.log(`\n[capture] ${manifest.length} screenshots in ${dir}`);
  } finally {
    await browser.close();
    vite.kill("SIGTERM");
  }
}

main().catch((err) => {
  console.error("[capture] failed:", err);
  process.exit(1);
});
