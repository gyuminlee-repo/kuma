/**
 * One-off capture of MAME phase tab 1 ("1. Custom Barcode Primer Design").
 *
 * Why a separate file instead of `capture-mame.ts --until 1`:
 * that harness's main() reads scripts/mame-real-data.json and hands the bundle
 * to buildSteps(), which dereferences `bundle.inputs.run_dir`. That file is
 * currently `{}` on this checkout, so buildSteps throws before any --until
 * limit is consulted. Regenerating it is out of scope (the nanopore run is not
 * on this machine), so the pieces needed here are copied rather than imported.
 *
 * Geometry matches the existing docs/screenshots-mame set byte-for-byte:
 * 1440x1120 CSS px at deviceScaleFactor 2 -> 2880x2240 PNG.
 *
 * Usage: node scripts/capture-mame-barcode-setup.mjs
 */

import { chromium } from "playwright";
import { spawn } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
// Not 1421: capture-mame.ts owns that port and another session may hold it.
const PORT = 1431;
const BASE_URL = `http://localhost:${PORT}`;
const VIEWPORT = { width: 1440, height: 1120 };
const SCALE = 2;
/** Cold dev-server transform of the whole source graph measured at 183s. */
const FIRST_LOAD_MS = 300_000;
const OUT = resolve(ROOT, "docs/screenshots-mame/13-barcode-package-setup.png");

// Bench filenames as recorded in scripts/gen_mame_capture_data.py DEFAULT_*.
// FileField renders the basename only, so the prefix is cosmetic; it is kept
// machine-neutral the way scripts/stubs/core.ts keeps PROJECT_ROOT neutral.
const BENCH_BASE = "~/_workspace/260730 MAME test";
const FASTA_PATH = `${BENCH_BASE}/pTSN-PtIspS-idi(KanR)_corrected.fa`;
const SEEDS_PATH = `${BENCH_BASE}/barcodes sequence.xlsx`;

async function portIsFree(url) {
  try {
    await fetch(url);
    return false; // something answered, so the port is held
  } catch {
    return true;
  }
}

function waitForServer(url, timeoutMs = 60_000) {
  const start = Date.now();
  return new Promise((ok, fail) => {
    const tick = async () => {
      try {
        const res = await fetch(url);
        if (res.status < 500) return ok();
      } catch {
        // connection refused until Vite binds
      }
      if (Date.now() - start > timeoutMs) {
        return fail(new Error(`Vite did not answer on ${url} within ${timeoutMs}ms`));
      }
      setTimeout(() => void tick(), 400);
    };
    void tick();
  });
}

async function startVite() {
  if (!(await portIsFree(BASE_URL))) {
    throw new Error(`port ${PORT} already answers; refusing to attach to another session's server`);
  }
  // No shell wrapper: it would absorb the kill and leave node holding the port.
  const child = spawn(
    process.execPath,
    [resolve(ROOT, "node_modules/vite/bin/vite.js"), "--port", String(PORT), "--strictPort"],
    { cwd: ROOT, env: { ...process.env, MOCK_MODE: "1" }, stdio: ["ignore", "pipe", "pipe"] },
  );
  child.stdout?.on("data", (d) => { const l = d.toString().trim(); if (l) console.log(`  [vite] ${l}`); });
  child.stderr?.on("data", (d) => { const l = d.toString().trim(); if (l) console.error(`  [vite:err] ${l}`); });
  await waitForServer(BASE_URL);
  return child;
}

async function main() {
  mkdirSync(dirname(OUT), { recursive: true });
  const vite = await startVite();
  const browser = await chromium.launch({ headless: true });
  const consoleErrors = [];
  const pageErrors = [];

  try {
    const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: SCALE });
    // updateCheck hits api.github.com on mount and raises a modal over whatever
    // is being shot when the answer lands.
    await context.route((url) => url.hostname.endsWith("github.com"), (route) => route.abort());
    const page = await context.newPage();
    page.on("console", (m) => { if (m.type() === "error") { consoleErrors.push(m.text()); console.warn(`  [browser:error] ${m.text()}`); } });
    page.on("pageerror", (e) => { pageErrors.push(String(e)); console.warn(`  [pageerror] ${String(e)}`); });

    console.log("[capture] navigating (cold transform, be patient)");
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: FIRST_LOAD_MS });
    await page.waitForFunction(() => typeof window.__store !== "undefined", { timeout: 60_000 });

    const card = page.locator("button, [role='button'], li, article")
      .filter({ hasText: "ispS_evolvepro_round1" }).first();
    await card.waitFor({ state: "visible", timeout: 30_000 });
    await card.click();
    await page.waitForFunction(
      () => Boolean(window.__store && "currentSubStep" in window.__store.getState()),
      { timeout: 30_000 },
    );
    // The external-database consent modal covers every later screen once raised.
    await page.evaluate(() => {
      window.__store?.setState({ networkConsentGranted: true, networkConsentPending: false });
    });

    const mameTab = page.getByRole("tab", { name: "Mame" });
    await mameTab.waitFor({ state: "visible", timeout: 30_000 });
    await mameTab.click();
    // MameTab is behind React.lazy and its chunk is transformed on demand.
    await page.locator('[role="tabpanel"] h1, [role="tabpanel"] h2, [role="tabpanel"] h3')
      .first().waitFor({ state: "visible", timeout: FIRST_LOAD_MS });
    console.log("[capture] MAME panel reached");

    // MamePhase initialises to "analyze" (phaseSlice.ts:36), so the setup tab
    // is an explicit click, not the landing state.
    const setupTab = page.getByRole("tab", { name: "1. Custom Barcode Primer Design" });
    await setupTab.waitFor({ state: "visible", timeout: 60_000 });
    await setupTab.click();
    // The panel's own "Barcode Package Setup" h2 is suppressed by `embedded`
    // (BarcodeSetupPanel.tsx:571, SetupStepView.tsx:67), so the on-screen
    // heading is WizardContainer's "Step 1.1: Barcode Package".
    await page.locator('[data-testid="wizard-header"] h2').filter({ hasText: "Barcode Package" })
      .first().waitFor({ state: "visible", timeout: 60_000 });
    await page.waitForTimeout(800);

    // Fill the two required pickers. FileField's input is unconditionally
    // readOnly, so paths arrive only through Browse, answered by the
    // MOCK_MODE dialog stub's queue. Queue order must match click order.
    await page.evaluate(([fasta, seeds]) => {
      window.__mockDialogQueue = { open: [fasta, seeds], save: [] };
    }, [FASTA_PATH, SEEDS_PATH]);
    for (const label of ["Browse CDS sequence", "Browse Barcode Seeds xlsx"]) {
      const btn = page.locator(`button[aria-label="${label}"]`).first();
      await btn.waitFor({ state: "visible", timeout: 20_000 });
      await btn.click();
      await page.waitForTimeout(700);
    }
    // Gene name last: browseFasta resets geneName to "" as part of its setForm.
    const geneName = page.locator("#gene-name");
    await geneName.waitFor({ state: "visible", timeout: 20_000 });
    await geneName.fill("IspS");
    await page.waitForTimeout(600);

    const filled = await page.evaluate(() => ({
      cds: document.querySelector('input[aria-label="CDS sequence"]')?.value ?? null,
      seeds: document.querySelector('input[aria-label="Barcode Seeds xlsx"]')?.value ?? null,
      gene: document.querySelector("#gene-name")?.value ?? null,
    }));
    console.log(`[capture] form values ${JSON.stringify(filled)}`);

    // Radix menus/popovers left open by an earlier click would ride into the shot.
    for (let i = 0; i < 3; i++) { await page.keyboard.press("Escape"); await page.waitForTimeout(150); }

    // Filling #gene-name makes Playwright scroll it into view, which leaves the
    // panel mid-scroll: the "Input files" heading and the CDS sequence row end
    // up above the fold. Wind both scroll containers back to the top so the
    // frame opens on the panel head, the way 02-inputs-filled.png does with its
    // scrollBy: 1. Blur too, so no field wears a focus ring in the shot.
    await page.evaluate(() => {
      document.activeElement?.blur?.();
      document.querySelectorAll('[data-testid="wizard-body"], .overflow-y-auto')
        .forEach((el) => { el.scrollTop = 0; });
    });
    await page.waitForTimeout(600);

    const tabState = await page.evaluate(() => {
      const el = [...document.querySelectorAll('[role="tab"]')]
        .find((n) => n.textContent?.includes("1. Custom Barcode Primer Design"));
      return el ? el.getAttribute("data-state") : null;
    });
    const mockHits = await page.locator("text=MOCK_MODE").count();
    const heading = await page.locator('[data-testid="wizard-header"] h2').first().innerText();

    await page.screenshot({ path: OUT, fullPage: false });
    console.log(`[capture] wrote ${OUT}`);
    console.log(`[verify] setupTab data-state=${tabState}`);
    console.log(`[verify] wizard heading=${JSON.stringify(heading)}`);
    console.log(`[verify] MOCK_MODE nodes in DOM=${mockHits}`);
    console.log(`[verify] console errors=${consoleErrors.length} pageerrors=${pageErrors.length}`);
    for (const e of [...new Set(consoleErrors)]) console.log(`[verify]   console: ${e}`);
    for (const e of [...new Set(pageErrors)]) console.log(`[verify]   pageerror: ${e}`);
    await context.close();
  } finally {
    await browser.close();
    vite.kill("SIGTERM");
  }
}

main().catch((err) => { console.error("[capture] failed:", err); process.exit(1); });
