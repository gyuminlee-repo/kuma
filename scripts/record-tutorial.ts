/**
 * KURO full-feature tutorial video recording — immersive cursor simulation.
 *
 * Usage: npm run record-tutorial
 *
 * Records a continuous .webm video showing ALL features with a visible macOS-style
 * cursor that moves smoothly between interactions.
 */

import { chromium, type Page } from "playwright";
import { spawn, type ChildProcess } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync, renameSync, rmSync } from "fs";
import { screenStates } from "./mock-data.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const DOCS_DIR = resolve(ROOT, "docs");
const VIDEO_TMP = resolve(DOCS_DIR, ".video-tmp");
const PORT = 1421;
const BASE_URL = `http://localhost:${PORT}`;

// ── macOS arrow cursor SVG (24×24) encoded as data URL ──────────────────────
const CURSOR_SVG_DATA = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M4 2 L4 20 L8.5 15.5 L12 22 L14 21 L10.5 14.5 L17 14.5 Z' fill='white' stroke='black' stroke-width='1.5' stroke-linejoin='round'/%3E%3C/svg%3E`;

// ── Environment helpers ──────────────────────────────────────────────────────

function buildEnv(): NodeJS.ProcessEnv {
  const existing = process.env.LD_LIBRARY_PATH ?? "";
  const condaLibPaths = [
    "/home/gml/miniforge3/lib",
    "/home/gml/anaconda3/lib",
    "/opt/conda/lib",
  ].filter((p) => existsSync(p));
  const ldPath = [...condaLibPaths, existing].filter(Boolean).join(":");
  return { ...process.env, LD_LIBRARY_PATH: ldPath || undefined };
}

function ensureDir(dir: string) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

function waitForServer(url: string, timeoutMs = 30_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const interval = setInterval(async () => {
      try {
        const res = await fetch(url);
        if (res.ok || res.status < 500) { clearInterval(interval); resolve(); }
      } catch {
        if (Date.now() - start > timeoutMs) { clearInterval(interval); reject(new Error("Server timeout")); }
      }
    }, 500);
  });
}

async function startViteServer(): Promise<ChildProcess> {
  console.log("[record] Starting Vite dev server (MOCK_MODE=1) ...");
  const child = spawn("npx", ["vite", "--port", String(PORT), "--strictPort"], {
    cwd: ROOT,
    env: { ...buildEnv(), MOCK_MODE: "1" },
    stdio: ["ignore", "pipe", "pipe"],
    shell: true,
  });
  child.stdout?.on("data", (d: Buffer) => { const l = d.toString().trim(); if (l) console.log(`  [vite] ${l}`); });
  child.stderr?.on("data", (d: Buffer) => { const l = d.toString().trim(); if (l && !l.includes("already in use")) console.error(`  [vite:err] ${l}`); });
  await waitForServer(BASE_URL);
  console.log("[record] Vite server ready.");
  return child;
}

// ── Cursor injection ─────────────────────────────────────────────────────────

async function injectCursor(page: Page): Promise<void> {
  await page.evaluate((cursorUrl: string) => {
    const existing = document.getElementById("__kuro_cursor");
    if (existing) existing.remove();

    const cursor = document.createElement("div");
    cursor.id = "__kuro_cursor";
    cursor.style.cssText = [
      "position: fixed",
      "z-index: 2147483647",
      "pointer-events: none",
      "width: 24px",
      "height: 24px",
      `background-image: url("${cursorUrl}")`,
      "background-repeat: no-repeat",
      "background-size: contain",
      "left: 100px",
      "top: 100px",
      "transition: left 0.28s cubic-bezier(0.25,0.46,0.45,0.94), top 0.28s cubic-bezier(0.25,0.46,0.45,0.94)",
    ].join(";");
    document.body.appendChild(cursor);
  }, CURSOR_SVG_DATA);
}

// ── Ripple click animation ───────────────────────────────────────────────────

async function showRipple(page: Page, x: number, y: number): Promise<void> {
  await page.evaluate(([cx, cy]: number[]) => {
    const ripple = document.createElement("div");
    ripple.style.cssText = [
      "position: fixed",
      "z-index: 2147483646",
      "pointer-events: none",
      `left: ${cx - 12}px`,
      `top: ${cy - 12}px`,
      "width: 24px",
      "height: 24px",
      "border-radius: 50%",
      "background: rgba(59,130,246,0.45)",
      "transform: scale(0)",
      "transition: transform 0.25s ease-out, opacity 0.25s ease-out",
      "opacity: 1",
    ].join(";");
    document.body.appendChild(ripple);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        ripple.style.transform = "scale(2.5)";
        ripple.style.opacity = "0";
        setTimeout(() => ripple.remove(), 350);
      });
    });
  }, [x, y]);
}

// ── Helper functions ─────────────────────────────────────────────────────────

/** Move cursor div to (x, y) and synchronize playwright mouse. */
async function moveTo(page: Page, x: number, y: number): Promise<void> {
  await page.evaluate(([cx, cy]: number[]) => {
    const cursor = document.getElementById("__kuro_cursor");
    if (cursor) { cursor.style.left = `${cx}px`; cursor.style.top = `${cy}px`; }
  }, [x, y]);
  await page.mouse.move(x, y);
  await page.waitForTimeout(320); // let CSS transition complete
}

/** Get bounding-box center of a locator. Returns null if not found. */
async function getCenter(page: Page, selector: string): Promise<{ x: number; y: number } | null> {
  try {
    const loc = page.locator(selector).first();
    const box = await loc.boundingBox({ timeout: 3000 });
    if (!box) return null;
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  } catch {
    return null;
  }
}

/** Move cursor to element center, show ripple, then click. */
async function clickAt(page: Page, selector: string): Promise<boolean> {
  const center = await getCenter(page, selector);
  if (!center) return false;
  await moveTo(page, center.x, center.y);
  await showRipple(page, center.x, center.y);
  await page.waitForTimeout(80);
  await page.locator(selector).first().click();
  return true;
}

/** Type text character by character with visible cursor position. */
async function typeText(
  page: Page,
  selector: string,
  text: string,
  delayMs = 50,
): Promise<void> {
  const center = await getCenter(page, selector);
  if (center) await moveTo(page, center.x, center.y);
  await showRipple(page, center?.x ?? 400, center?.y ?? 300);
  await page.locator(selector).first().click();
  for (const char of text) {
    await page.keyboard.type(char);
    await page.waitForTimeout(delayMs);
  }
}

/** Convenience wait. */
async function wait(page: Page, ms: number): Promise<void> {
  await page.waitForTimeout(ms);
}

// ── Inject Zustand state ─────────────────────────────────────────────────────

async function inject(page: Page, state: Record<string, unknown>): Promise<void> {
  await page.evaluate((s: Record<string, unknown>) => {
    const store = (window as unknown as Record<string, unknown>).__store as {
      setState: (state: Record<string, unknown>) => void;
    };
    store.setState(s);
  }, state);
  await page.waitForTimeout(400);
}

// ── Progress animation helper ────────────────────────────────────────────────

async function animateProgress(page: Page, baseState: Record<string, unknown>): Promise<void> {
  for (const pct of [0, 15, 35, 55, 75, 90, 100]) {
    await inject(page, {
      ...baseState,
      progress: pct,
      isDesigning: pct < 100,
      statusMessage: pct < 100 ? `Designing... ${pct}%` : "95/95 designed | Tm condition: 95/95",
    });
    await page.waitForTimeout(pct === 100 ? 600 : 280);
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  ensureDir(DOCS_DIR);
  ensureDir(VIDEO_TMP);

  const env = buildEnv();
  if (env.LD_LIBRARY_PATH) process.env.LD_LIBRARY_PATH = env.LD_LIBRARY_PATH;

  const vite = await startViteServer();
  let browser;

  try {
    browser = await chromium.launch({
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
      ],
    });

    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      deviceScaleFactor: 1,
      recordVideo: { dir: VIDEO_TMP, size: { width: 1280, height: 800 } },
    });

    const page = await context.newPage();
    page.on("console", () => {});

    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.waitForFunction(
      () => typeof (window as unknown as Record<string, unknown>).__store !== "undefined",
      { timeout: 10_000 },
    );

    await injectCursor(page);
    console.log("[record] Recording 13 scenes ...\n");

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 1: Initial empty screen
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  1/13  Initial empty screen");
    await inject(page, screenStates[0].state);
    // Cursor parks near Browse button area
    await moveTo(page, 640, 400);
    await wait(page, 2000);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 2: Browse click → file loaded
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  2/13  Browse → file loaded");
    // Move toward Browse button, click it (file dialog is mocked — inject state directly)
    const browseOk = await clickAt(page, "button:has-text('Browse')");
    if (!browseOk) {
      // fallback: move to approximate position
      await moveTo(page, 200, 155);
      await showRipple(page, 200, 155);
    }
    await wait(page, 400);
    await inject(page, screenStates[1].state);
    await wait(page, 2500);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 3: Gene selection dropdown open
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  3/13  Gene selection dropdown");
    const geneSelectCenter = await getCenter(page, "select");
    if (geneSelectCenter) {
      await moveTo(page, geneSelectCenter.x, geneSelectCenter.y);
      await showRipple(page, geneSelectCenter.x, geneSelectCenter.y);
      await page.locator("select").first().focus();
    }
    await wait(page, 1500);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 4: EVOLVEpro mode — tab click, CSV Browse, state injection
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  4/13  EVOLVEpro CSV loaded");
    // Click EVOLVEpro tab/radio
    const evolveOk = await clickAt(page, "[role=radio]:has-text('EVOLVEpro'), button:has-text('EVOLVEpro'), label:has-text('EVOLVEpro')");
    if (!evolveOk) await clickAt(page, "input[value='evolvepro']");
    await wait(page, 600);
    // Click Browse for CSV
    const browseCsv = await clickAt(page, "button:has-text('Browse')");
    if (!browseCsv) await moveTo(page, 200, 250);
    await wait(page, 400);
    await inject(page, screenStates[2].state);
    await wait(page, 2500);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 5: Advanced options panel
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  5/13  Advanced options panel");
    const advOk = await clickAt(page, "button:has-text('Advanced')");
    if (!advOk) await moveTo(page, 640, 350);
    await wait(page, 2000);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 6: Design Primers → progress animation → result table (95 entries)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  6/13  Design Primers → result table (95 entries)");
    const designOk = await clickAt(page, "button:has-text('Design Primers'), button:has-text('Design')");
    if (!designOk) await moveTo(page, 640, 470);
    await wait(page, 400);

    const progressBase: Record<string, unknown> = {
      ...screenStates[3].state,
      designResults: [],
      plateMappings: [],
      successCount: 0,
      totalCount: 95,
    };
    await animateProgress(page, progressBase);

    // Final — inject full result
    await inject(page, screenStates[3].state);
    await moveTo(page, 640, 500);
    await wait(page, 3000);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 7: Sort by Mutation header (asc → desc)
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  7/13  Sort by Mutation column");
    const mutHeader = page.locator("th:has-text('Mutation'), th:has-text('mutation')").first();
    const mutBox = await mutHeader.boundingBox().catch(() => null);
    if (mutBox) {
      const mx = mutBox.x + mutBox.width / 2;
      const my = mutBox.y + mutBox.height / 2;
      await moveTo(page, mx, my);
      await showRipple(page, mx, my);
      await mutHeader.click();
      await wait(page, 1800);
      await showRipple(page, mx, my);
      await mutHeader.click();
      await wait(page, 1500);
    } else {
      await wait(page, 3000);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 8: Click Forward primer cell → candidate popover → close
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  8/13  Forward primer candidate popover");
    const fwdCell = page.locator("td.cursor-pointer").first();
    const fwdBox = await fwdCell.boundingBox().catch(() => null);
    if (fwdBox) {
      const fx = fwdBox.x + fwdBox.width / 2;
      const fy = fwdBox.y + fwdBox.height / 2;
      await moveTo(page, fx, fy);
      await showRipple(page, fx, fy);
      await fwdCell.click();
      await wait(page, 3000);
      // Close popover
      const backdrop = page.locator(".fixed.inset-0").first();
      if (await backdrop.count() > 0) {
        await backdrop.click({ position: { x: 10, y: 10 } });
      } else {
        await page.keyboard.press("Escape");
      }
      await wait(page, 500);
    } else {
      await wait(page, 3500);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 9: HP/Hairpin detail cell → popover → close
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  9/13  Hairpin detail popover");
    const hpCells = page.locator("td.cursor-pointer");
    const hpCount = await hpCells.count();
    let hpClicked = false;
    for (let i = 0; i < hpCount; i++) {
      const text = (await hpCells.nth(i).textContent()) ?? "";
      const num = parseFloat(text);
      if (!isNaN(num) && num > 0 && !text.includes("!!") && !text.includes("OK")) {
        const box = await hpCells.nth(i).boundingBox().catch(() => null);
        if (box) {
          const hx = box.x + box.width / 2;
          const hy = box.y + box.height / 2;
          await moveTo(page, hx, hy);
          await showRipple(page, hx, hy);
          await hpCells.nth(i).click();
          await wait(page, 2500);
          const backdrop = page.locator(".fixed.inset-0").first();
          if (await backdrop.count() > 0) {
            await backdrop.click({ position: { x: 10, y: 10 } });
          } else {
            await page.keyboard.press("Escape");
          }
          await wait(page, 500);
          hpClicked = true;
          break;
        }
      }
    }
    if (!hpClicked) await wait(page, 3000);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 10: Plate Map — Forward tab
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  10/13 Plate Map — Forward tab");
    await inject(page, screenStates[4].state);
    // Scroll down to plate map area
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await wait(page, 600);
    // Try to click Forward tab
    const fwdTab = page.locator("button:has-text('Forward'), [role=tab]:has-text('Forward')").first();
    const fwdTabBox = await fwdTab.boundingBox().catch(() => null);
    if (fwdTabBox) {
      await moveTo(page, fwdTabBox.x + fwdTabBox.width / 2, fwdTabBox.y + fwdTabBox.height / 2);
    }
    await wait(page, 2000);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 11: Plate Map — Reverse tab
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  11/13 Plate Map — Reverse tab");
    const revTabOk = await clickAt(page, "button:has-text('Reverse'), [role=tab]:has-text('Reverse')");
    if (!revTabOk) await moveTo(page, 700, 600);
    await wait(page, 2000);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 12: File menu → open → close
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  12/13 File menu");
    await page.evaluate(() => window.scrollTo(0, 0));
    await wait(page, 300);
    const fileOk = await clickAt(page, "button:has-text('File')");
    if (!fileOk) await moveTo(page, 50, 30);
    await wait(page, 2000);
    await moveTo(page, 50, 30);
    await page.keyboard.press("Escape");
    await wait(page, 500);

    // ─────────────────────────────────────────────────────────────────────────
    // Scene 13: Help > About
    // ─────────────────────────────────────────────────────────────────────────
    console.log("  13/13 Help > About");
    const helpOk = await clickAt(page, "button:has-text('Help')");
    if (!helpOk) await moveTo(page, 100, 30);
    await wait(page, 500);
    const aboutOk = await clickAt(page, "[role=menuitem]:has-text('About')");
    if (!aboutOk) await moveTo(page, 130, 60);
    await wait(page, 2500);

    // ─────────────────────────────────────────────────────────────────────────
    // Finalize
    // ─────────────────────────────────────────────────────────────────────────
    const videoPath = await page.video()?.path();
    await context.close();

    if (videoPath && existsSync(videoPath)) {
      const dest = resolve(DOCS_DIR, "tutorial.webm");
      if (existsSync(dest)) rmSync(dest);
      renameSync(videoPath, dest);
      console.log(`\n[record] Video saved: docs/tutorial.webm`);
    } else {
      console.warn("[record] Warning: video file not found after context close.");
    }

    console.log("[record] Done — 13 scenes recorded.");
  } finally {
    if (browser) await browser.close();
    vite.kill();
    try { rmSync(VIDEO_TMP, { recursive: true, force: true }); } catch { /* ignore */ }
    console.log("[record] Vite server stopped.");
  }
}

main().catch((err) => {
  console.error("[record] Fatal error:", err);
  process.exit(1);
});
