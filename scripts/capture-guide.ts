/**
 * KURO guide screenshot capture script.
 *
 * Usage: npm run capture-guide
 *
 * Starts a Vite dev server with MOCK_MODE=1, then uses Playwright
 * Chromium to capture each screen state defined in mock-data.ts.
 * Screenshots are saved to docs/screenshots/XX-name.png.
 */

import { chromium } from "playwright";
import { spawn, type ChildProcess } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync } from "fs";
import { screenStates } from "./mock-data.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SCREENSHOTS_DIR = resolve(ROOT, "docs", "screenshots");
const PORT = 1421;
const BASE_URL = `http://localhost:${PORT}`;

// WSL2: Playwright Chromium needs libraries from conda/miniforge.
// Detect and prepend to LD_LIBRARY_PATH automatically.
function buildEnv(): NodeJS.ProcessEnv {
  const existing = process.env.LD_LIBRARY_PATH ?? "";
  const condaLibPaths = [
    "/home/gml/miniforge3/lib",
    "/home/gml/anaconda3/lib",
    "/opt/conda/lib",
  ].filter((p) => existsSync(p));

  const ldPath = [...condaLibPaths, existing].filter(Boolean).join(":");
  return {
    ...process.env,
    LD_LIBRARY_PATH: ldPath || undefined,
  };
}

function ensureDir(dir: string) {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

function waitForServer(url: string, timeoutMs = 30_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const interval = setInterval(async () => {
      try {
        const res = await fetch(url);
        if (res.ok || res.status < 500) {
          clearInterval(interval);
          resolve();
        }
      } catch {
        if (Date.now() - start > timeoutMs) {
          clearInterval(interval);
          reject(new Error(`Server at ${url} did not start within ${timeoutMs}ms`));
        }
      }
    }, 500);
  });
}

async function startViteServer(): Promise<ChildProcess> {
  console.log("[capture] Starting Vite dev server (MOCK_MODE=1) ...");

  const child = spawn("npx", ["vite", "--port", String(PORT), "--strictPort"], {
    cwd: ROOT,
    env: { ...buildEnv(), MOCK_MODE: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    shell: true,
  });

  child.stdout?.on("data", (data: Buffer) => {
    const line = data.toString().trim();
    if (line) console.log(`  [vite] ${line}`);
  });
  child.stderr?.on("data", (data: Buffer) => {
    const line = data.toString().trim();
    if (line) console.error(`  [vite:err] ${line}`);
  });

  await waitForServer(BASE_URL);
  console.log("[capture] Vite server ready.");
  return child;
}

async function main() {
  ensureDir(SCREENSHOTS_DIR);

  const env = buildEnv();
  if (env.LD_LIBRARY_PATH) {
    console.log(`[capture] LD_LIBRARY_PATH=${env.LD_LIBRARY_PATH}`);
    process.env.LD_LIBRARY_PATH = env.LD_LIBRARY_PATH;
  }

  const vite = await startViteServer();

  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
      ],
    });

    const context = await browser.newContext({
      viewport: { width: 1200, height: 800 },
      deviceScaleFactor: 2,
    });

    const page = await context.newPage();

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        console.warn(`  [browser:error] ${msg.text()}`);
      }
    });

    for (const screen of screenStates) {
      console.log(`[capture] Capturing: ${screen.name}`);

      await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(800);

      await page.waitForFunction(
        () => typeof (window as unknown as Record<string, unknown>).__store !== "undefined",
        { timeout: 10_000 },
      );

      await page.evaluate((state: Record<string, unknown>) => {
        type StoreApi = {
          setState: (state: Record<string, unknown>) => void;
        };
        const store = (window as unknown as Record<string, unknown>).__store as StoreApi;
        store.setState(state);
      }, screen.state);

      await page.waitForTimeout(500);

      if (screen.action) {
        await page.evaluate(screen.action);
        await page.waitForTimeout(300);
      }

      const outPath = resolve(SCREENSHOTS_DIR, `${screen.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> saved: docs/screenshots/${screen.name}.png`);
    }

    await context.close();
    console.log(`\n[capture] Done. ${screenStates.length} screenshots saved to docs/screenshots/`);
  } finally {
    if (browser) await browser.close();
    vite.kill();
    console.log("[capture] Vite server stopped.");
  }
}

main().catch((err) => {
  console.error("[capture] Fatal error:", err);
  process.exit(1);
});
