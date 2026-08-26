/**
 * MAME screenshot capture backed by real sidecar output.
 *
 * The KURO harness (capture-real.ts) injects store state, which it can do
 * because src/main.tsx exposes `useAppStore` as `window.__store` in dev builds.
 * It does not expose `useMameAppStore`, and adding it would be a src/ change
 * made solely to take screenshots. So this harness drives the UI instead:
 * it clicks the wizard the way an operator does, and the store fills through
 * the app's own handlers.
 *
 * That makes it slower and more brittle than injection, and better evidence.
 * A screen here is one the application actually reached, not one assembled
 * around it. Every value on screen still comes from the sidecar, served out of
 * scripts/mame-real-data.json by scripts/stubs/core.ts.
 *
 * MAME input rows are `FileField`, whose text input is unconditionally
 * readOnly, so paths cannot be typed. They arrive through the Browse button,
 * which calls the plugin-dialog stub; the stub answers from a queue this file
 * seeds (`window.__mockDialogQueue`).
 *
 * Usage:
 *   python3 scripts/gen_mame_capture_data.py
 *   pnpm exec tsx scripts/capture-mame.ts [--out docs/screenshots-mame] [--until 4]
 */

import { chromium, type Page } from "playwright";
import { spawn, execFileSync, type ChildProcess } from "child_process";
import { createRequire } from "module";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync, writeFileSync } from "fs";

declare global {
  interface Window {
    __store?: {
      getState: () => Record<string, unknown>;
      setState: (partial: Record<string, unknown>) => void;
    };
    __mockDialogQueue?: {
      open?: Array<string | string[] | null>;
      save?: Array<string | null>;
    };
  }
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const PORT = 1421;
const BASE_URL = `http://localhost:${PORT}`;
const VIEWPORT = { width: 1440, height: 1120 };
const BUNDLE_PATH = resolve(ROOT, "scripts/mame-real-data.json");

interface MameBundle {
  /** The paths the generator sent the sidecar, so both drive the same run. */
  inputs: {
    run_dir: string;
    barcodes: string;
    expected: string;
    reference: string;
    output_dir: string;
  };
}

interface Step {
  name: string;
  caption: string;
  /** Paths the next Browse clicks should answer with, in order. */
  dialogPaths?: string[];
  /** Playwright selectors clicked in order before the shot. */
  clicks?: string[];
  /** Selector that must be visible before the shot. A miss aborts the run. */
  expect?: string;
  /**
   * Keep whatever layer is open coming into this step.
   *
   * Steps normally start by pressing Escape, because a Radix menu left open by
   * one screen otherwise rides into the next. A dialog the wizard raised on
   * purpose, though, is the thing the next step has to click, and Escape
   * dismisses it before the click lands.
   */
  keepOverlay?: boolean;
  /**
   * Longer wait for this step's clicks and marker.
   *
   * The analyze reply is held back for as long as the sidecar really took, so
   * the controls that appear when the run finishes are minutes away, not
   * seconds. Only the step that waits on a run raises this; leaving the
   * default everywhere else keeps a genuine miss fast to spot.
   */
  slowMs?: number;
  /**
   * Pixels to scroll the wizard body down before the shot.
   *
   * The review step is taller than the viewport. Scrolling an element into
   * view does not work here: the wizard body is its own scroll container, so
   * scrollIntoView moves the page around it and the panel stays below the
   * fold. Driving that container directly is what actually moves.
   */
  scrollBy?: number;
}

function outputDir(): string {
  const flagIndex = process.argv.indexOf("--out");
  const relative = flagIndex >= 0 ? process.argv[flagIndex + 1] : "docs/screenshots-mame";
  return resolve(ROOT, relative);
}

function untilStep(): number {
  const flagIndex = process.argv.indexOf("--until");
  return flagIndex >= 0 ? Number(process.argv[flagIndex + 1]) : Number.POSITIVE_INFINITY;
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

/** Walk the project picker into the workspace, then switch to the MAME tab. */
async function enterMame(page: Page): Promise<void> {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => typeof window.__store !== "undefined", { timeout: 20_000 });

  const card = page
    .locator("button, [role='button'], li, article")
    .filter({ hasText: "ispS_evolvepro_round1" })
    .first();
  await card.waitFor({ state: "visible", timeout: 20_000 });
  await card.click();

  await page.waitForFunction(
    () => Boolean(window.__store && "currentSubStep" in window.__store.getState()),
    { timeout: 20_000 },
  );
  // The external-database consent modal covers every later screen once raised.
  // Marked settled up front rather than dismissed per screen.
  await page.evaluate(() => {
    window.__store?.setState({ networkConsentGranted: true, networkConsentPending: false });
  });

  const mameTab = page.getByRole("tab", { name: "Mame" });
  await mameTab.waitFor({ state: "visible", timeout: 20_000 });
  await mameTab.click();
  // MameTab is behind React.lazy; wait for the tab panel to hold something,
  // not a fixed sleep. Which step it opens on is the wizard's decision, so the
  // wait is on the panel rather than on a named step.
  await page
    .locator('[role="tabpanel"] h1, [role="tabpanel"] h2, [role="tabpanel"] h3')
    .first()
    .waitFor({ state: "visible", timeout: 30_000 });
  if (process.argv.includes("--debug")) {
    const headings = await page
      .locator('[role="tabpanel"] h1, [role="tabpanel"] h2, [role="tabpanel"] h3, [role="tabpanel"] button')
      .allInnerTexts();
    console.log("[debug] MAME panel:", JSON.stringify(headings.slice(0, 40)));
  }
}

async function dismissOverlays(page: Page): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(120);
  }
}

/**
 * `soft` is the harvest pass, used while building the step list: it reports a
 * selector that matches nothing and walks on, so one run reaches the later
 * screens and names every missing sidecar reply at once. A capture run is
 * never soft. A miss there yields a screenshot that contradicts its own
 * filename, so it aborts.
 */
async function runStep(page: Page, step: Step, soft: boolean): Promise<void> {
  const clickTimeout = step.slowMs ?? (soft ? 5_000 : 15_000);
  const markerTimeout = step.slowMs ?? (soft ? 5_000 : 20_000);
  if (step.dialogPaths) {
    const paths = step.dialogPaths;
    await page.evaluate((queued) => {
      window.__mockDialogQueue = { open: [...queued], save: [...queued] };
    }, paths);
  }

  for (const selector of step.clicks ?? []) {
    const target = page.locator(selector).first();
    if (soft && (await target.count()) === 0) {
      console.warn(`  [harvest] ${step.name}: no element for ${selector}`);
      continue;
    }
    await target.waitFor({ state: "visible", timeout: clickTimeout });
    // Radix menus and popovers open on pointerdown, which a JS .click() never
    // dispatches, so every click here goes through real input.
    await target.click();
    await page.waitForTimeout(500);
  }

  if (step.scrollBy) {
    const moved = await page.evaluate((amount) => {
      const body = document.querySelector('[data-testid="wizard-body"]');
      if (!body) return false;
      body.scrollTop = amount;
      return body.scrollTop > 0;
    }, step.scrollBy);
    if (!moved && !soft) {
      throw new Error(`${step.name}: wizard body did not scroll`);
    }
    await page.waitForTimeout(400);
  }

  if (step.expect) {
    const marker = page.locator(step.expect).first();
    if (soft && (await marker.count()) === 0) {
      console.warn(`  [harvest] ${step.name}: expect missed ${step.expect}`);
    } else {
      await marker.waitFor({ state: "visible", timeout: markerTimeout });
    }
  }
  await page.waitForTimeout(600);
}

function buildSteps(bundle: MameBundle): Step[] {
  const lab = bundle.inputs;
  return [
    {
      name: "01-inputs-empty",
      caption: "MAME opens on its input step with nothing chosen yet.",
      expect: "text=Input files",
    },
    {
      name: "02-inputs-filled",
      caption:
        "The run folder, the custom barcode sheet, and the expected variant list, named as they sit on the bench.",
      // Queue order must match click order: the stub shifts one entry per
      // Browse press, so a mismatch silently files a path under the wrong row.
      dialogPaths: [lab.run_dir, lab.barcodes, lab.expected, lab.reference, lab.output_dir],
      clicks: [
        'button[aria-label="Browse MinKNOW run folder"]',
        'button[aria-label="Browse Custom Barcodes (xlsx or csv)"]',
        'button[aria-label="Browse Expected variants (xlsx)"]',
        'button[aria-label="Browse Reference construct"]',
        'button[aria-label="Browse Export destination folder"]',
      ],
      scrollBy: 1,
    },
    {
      name: "03-inputs-detail",
      caption:
        "The rest of the same panel: where output lands, and the draft placement the plate opens on, 96 wells holding 95 variants and the wild-type control.",
      scrollBy: 700,
    },
    {
      name: "04-parameters",
      caption:
        "The thresholds this run scores against: amplicon mode on a MinKNOW raw run, 30 filtered reads per well, at most 5 unexpected amino-acid changes, and no consensus N tolerated.",
      scrollBy: 1800,
    },
    {
      name: "05-validated",
      caption:
        "Validation runs before any demux and reads the barcode sheet: 12 forward by 8 reverse seeds, 96 wells on one plate.",
      clicks: ['button:has-text("Validate")'],
      expect: "text=Validation complete",
      scrollBy: 1,
    },
    {
      name: "06-preflight",
      caption:
        "The pre-flight check every run passes through. The disk-space warning is unconditional: no cross-platform API reports free space, so the app says so rather than guessing.",
      // The wizard footer button, not the "Run" menu in the menu bar. Only the
      // footer carries an aria-label, and a text match takes the menu first.
      clicks: ['button[aria-label="Run"]'],
      expect: "text=Pre-flight check",
    },
    {
      name: "07-native-barcodes",
      caption:
        "Three native barcodes carried this run, holding between a quarter and two fifths of the sequencing volume each. Choosing them as replicates is what makes this three plates rather than one pool.",
      keepOverlay: true,
      clicks: ['button:has-text("Continue with warnings")'],
      expect: "text=Select the replicate axis for this run",
    },
    {
      name: "08-run-quality",
      caption:
        "What the run says about itself before a verdict is read: median depth 571 against a recommended 1500, the amplicon window the reads covered, and where stray reads went.",
      keepOverlay: true,
      // :text-is, not :has-text. The latter is a case-insensitive substring
      // match, so "Run" also selects the dialog's "Cancel run" button, which
      // sits first in the DOM and silently abandons the run.
      //
      // The completion dialog is dismissed rather than captured: it reports an
      // elapsed time measured against the recorded reply, and capturing that
      // would state a runtime nobody will see.
      clicks: ['[role="dialog"] button:text-is("Run")', 'button:text-is("Close")'],
      // The Close button arrives only when the analyze reply does.
      slowMs: 600_000,
      expect: "text=Step 2.2",
    },
    {
      name: "09-verdict-plate",
      caption:
        "94 of 95 designed mutants recovered. The plate carries the variant each well was meant to hold, and the verdict table splits the same wells by replicate barcode.",
      scrollBy: 900,
    },
    {
      name: "10-replicate-distribution",
      caption:
        "The same 288 verdicts as a per-plate distribution: 81, 84 and 78 per cent pass across NB07, NB08 and NB09, with the failure classes broken out beside the rows they came from.",
      scrollBy: 1500,
    },
    {
      name: "11-janus-settings",
      caption:
        "The optional Janus step. The analyze run already wrote the pick list of 94 clones; only the instrument sheet waits on a transfer volume and liquid class being named here.",
      clicks: ["text=3. Janus Setup"],
      expect: "text=Step 3.1",
    },
    {
      name: "12-activity-data",
      caption:
        "The activity step, empty: this run carries sequencing verdicts only, with no assay readings uploaded yet.",
      clicks: ["text=4. Activity Data"],
      expect: "text=Step 4.1",
    },
  ];
}

async function main(): Promise<void> {
  const dir = outputDir();
  if (!existsSync(BUNDLE_PATH)) {
    throw new Error(
      "scripts/mame-real-data.json missing. Run scripts/gen_mame_capture_data.py first.",
    );
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const bundle = createRequire(import.meta.url)("./mame-real-data.json") as MameBundle;
  mkdirSync(dir, { recursive: true });

  const harvest = process.argv.includes("--harvest");
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
      if (text.includes("MOCK_MODE")) gaps.push(text);
    });

    await enterMame(page);

    const limit = untilStep();
    for (const [index, step] of buildSteps(bundle).entries()) {
      if (index + 1 > limit) break;
      console.log(`[capture] ${step.name}`);
      if (!step.keepOverlay) await dismissOverlays(page);
      await runStep(page, step, harvest);
      const file = `${step.name}.png`;
      await page.screenshot({ path: resolve(dir, file), fullPage: false });
      manifest.push({ name: step.name, caption: step.caption, file });
    }

    if (gaps.length > 0 && harvest) {
      // Development aid: list every missing reply in one pass so the generator
      // can be extended once, instead of re-running the analyze for each gap.
      console.log("\n[harvest] missing sidecar replies:");
      for (const gap of [...new Set(gaps)]) console.log(`  ${gap}`);
    } else if (gaps.length > 0) {
      // Any MOCK_MODE text reaching the UI ends up in a status bar or banner
      // and rides into a frame, so the set is not publishable until the
      // generator records that reply or the stub grows that command.
      throw new Error(`MOCK_MODE gaps reached the UI: ${[...new Set(gaps)].join(", ")}`);
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
