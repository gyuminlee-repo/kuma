/**
 * One-off capture of MAME sub-step `activity.signals` (rail label 4.2), the
 * last screen of the MAME wizard.
 *
 * Why a separate file instead of a step appended to `capture-mame.ts`:
 * that harness's main() hands scripts/mame-real-data.json to buildSteps(),
 * which dereferences `bundle.inputs.run_dir` while building the array. That
 * file is `{}` on this checkout, so buildSteps throws before any `--until`
 * limit is read, and regenerating it needs the nanopore run (not on this
 * machine). scripts/capture-mame-barcode-setup.mjs was written for the same
 * reason and this follows it.
 *
 * Why the rail rather than walking the wizard: MameWorkflowRail's onStepClick
 * navigates unconditionally (MameWorkflowRail.tsx:187-193), and WorkflowRail
 * states outright that every rail item stays clickable and that the guard
 * lives on the Next button (WorkflowRail.tsx:107-109). So 4.2 is reachable
 * without replaying the analyze run, which is what the recorded sidecar reply
 * would otherwise hold this script open for.
 *
 * Nothing is clicked that would need a reply the MOCK_MODE stub does not
 * carry. `strategy.classify_round` has no entry in scripts/stubs/core.ts, so
 * pressing "Run classification" would paint a MOCK_MODE error into the frame.
 * The screen is captured in the state the app actually reaches here.
 *
 * Geometry matches the existing docs/screenshots-mame set:
 * 1440x1120 CSS px at deviceScaleFactor 2 -> 2880x2240 PNG.
 *
 * Usage: node scripts/capture-mame-activity-signals.mjs
 */

import { chromium } from "playwright";
import { spawn } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync } from "fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
// Not 1421 (capture-mame.ts) and not 1431 (capture-mame-barcode-setup.mjs):
// another session may hold either, and attaching would shoot its build.
const PORT = 1441;
const BASE_URL = `http://localhost:${PORT}`;
const VIEWPORT = { width: 1440, height: 1120 };
const SCALE = 2;
/** Cold dev-server transform of the whole source graph measured at 183s. */
const FIRST_LOAD_MS = 300_000;
// 13-barcode-package-setup.png already occupies 13 in this directory
// (commit faca1c68), so the next free ordinal is 14.
const OUT = resolve(ROOT, "docs/screenshots-mame/14-activity-signals.png");

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

    // MamePhase initialises to "analyze" (phaseSlice.ts:36), so the activity
    // phase tab is an explicit click. It lands on 4.1, the phase's first
    // sub-step (MAME_SUBSTEP_ORDER.activity).
    const activityTab = page.getByRole("tab", { name: "4. Activity Data" });
    await activityTab.waitFor({ state: "visible", timeout: 60_000 });
    await activityTab.click();
    await page.locator('[data-testid="wizard-header"] h2').filter({ hasText: "Step 4.1" })
      .first().waitFor({ state: "visible", timeout: 60_000 });
    console.log("[capture] step 4.1 reached");

    // The rail row carries the sub-step title as its aria-label
    // (WorkflowRail.tsx:124-126); "Signals & Handoff" is
    // phaseC.mameSubSteps.activity.signals in src/locales/en.json.
    const railSignals = page.locator('button[aria-label="Signals & Handoff"]').first();
    await railSignals.waitFor({ state: "visible", timeout: 30_000 });
    await railSignals.click();
    await page.locator('[data-testid="wizard-header"] h2').filter({ hasText: "Step 4.2" })
      .first().waitFor({ state: "visible", timeout: 60_000 });
    console.log("[capture] step 4.2 reached");
    await page.waitForTimeout(1200);

    // Radix menus/popovers left open by an earlier click would ride into the shot.
    for (let i = 0; i < 3; i++) { await page.keyboard.press("Escape"); await page.waitForTimeout(150); }
    // Blur so no field wears a focus ring, and wind both scroll containers back
    // to the top so the frame opens on the panel head.
    await page.evaluate(() => {
      document.activeElement?.blur?.();
      document.querySelectorAll('[data-testid="wizard-body"], .overflow-y-auto')
        .forEach((el) => { el.scrollTop = 0; });
    });
    await page.waitForTimeout(600);

    const probe = await page.evaluate(() => {
      const text = (el) => (el ? el.innerText.replace(/\s+\n/g, "\n").trim() : null);
      const railActive = [...document.querySelectorAll('[aria-current="step"]')]
        .map((el) => el.innerText.replace(/\n+/g, " | ").trim());
      const header = document.querySelector('[data-testid="wizard-header"]');
      const body = document.querySelector('[data-testid="wizard-body"]');
      const footer = document.querySelector('[data-testid="wizard-container"] footer');
      const buttons = [...(body?.querySelectorAll("button") ?? [])].map((b) => ({
        text: b.innerText.trim(),
        aria: b.getAttribute("aria-label"),
        disabled: b.disabled,
      }));
      const inputs = [...(body?.querySelectorAll("input") ?? [])].map((i) => ({
        id: i.id, value: i.value, type: i.type,
      }));
      const footerButtons = [...(footer?.querySelectorAll("button") ?? [])].map((b) => ({
        text: b.innerText.trim(), disabled: b.disabled,
      }));
      return {
        railActive,
        header: text(header),
        body: text(body),
        bodyHeightPx: body ? Math.round(body.getBoundingClientRect().height) : null,
        contentHeightPx: body?.firstElementChild
          ? Math.round(body.firstElementChild.getBoundingClientRect().height)
          : null,
        footer: text(footer),
        footerButtons,
        buttons,
        inputs,
        advisoryHeading: text(document.querySelector("#advisory-decision-heading")),
        fileRows: document.querySelectorAll('[aria-label="Selected round xlsx files"] li').length,
        cannotBeAssessed: document.body.innerText.includes("Cannot be assessed"),
        mockNodes: document.body.innerText.includes("MOCK_MODE"),
      };
    });

    await page.screenshot({ path: OUT, fullPage: false });
    console.log(`[capture] wrote ${OUT}`);
    console.log("[verify] " + JSON.stringify(probe, null, 2));
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
