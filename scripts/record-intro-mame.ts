/**
 * MAME intro video segment, recorded from the running dev build.
 *
 * This is capture-mame.ts with the screenshot loop replaced by the timeline
 * machinery from record-intro.ts. The two halves are kept apart on purpose:
 *
 *   - driving comes from capture-mame.ts. MAME state is not injectable, because
 *     src/main.tsx exposes `useAppStore` as `window.__store` and never exposes
 *     `useMameAppStore`. So the wizard is clicked the way an operator clicks it
 *     and the store fills through the app's own handlers, with every value on
 *     screen served out of scripts/mame-real-data.json by scripts/stubs/core.ts.
 *   - recording comes from record-intro.ts. The context is opened with
 *     recordVideo at native 1080p, each beat dwells for a fixed hold, and
 *     timeline-mame.json records where each beat actually landed.
 *
 * Because the driving is a click sequence rather than state injection, the beat
 * order and the driving order are different problems. The wizard has to be
 * walked 01 -> 10 no matter what the film shows, so this file walks all of it
 * and only holds the camera on the beats TIMELINE names. A beat whose screen
 * was already passed (08 after 10, the same review page scrolled back up) is
 * revisited by scrolling alone, never by replaying its clicks: step 08's clicks
 * start the analyze, and replaying them would start a second run.
 *
 * The full run records roughly 83 seconds of progress screen between beat 07
 * and beat 09. That is not a hang. scripts/mame-real-data.json carries
 * `analyze_seconds: 82.8` and the stub holds the reply back for exactly that
 * long, because the app times the call client-side and prints the result on the
 * review screen. Shortening it would put a runtime on film that no operator
 * will ever see. It is transition footage, charged to actualStartMs the same
 * way record-intro.ts charges its setup, and the editor cuts it using
 * timeline-mame.json. `--probe` stops before the analyze, so iteration is fast.
 *
 * Kept verbatim from both parents because the failure modes are identical:
 *   - the run refuses to start when port 1421 is already taken
 *   - Vite is spawned without a shell, so the kill reaches the node process
 *   - MOCK_MODE text reaching the UI fails the run
 *
 * Usage:
 *   pnpm exec tsx scripts/record-intro-mame.ts [--probe] [--out docs/.intro-video]
 */

import { chromium, type Page } from "playwright";
import { spawn, execFileSync, type ChildProcess } from "child_process";
import { createRequire } from "module";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync, writeFileSync, renameSync } from "fs";

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
/** Native 1080p. deviceScaleFactor stays 1: a 2x buffer only inflates the file. */
const VIEWPORT = { width: 1920, height: 1080 };
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

/** Identical to capture-mame.ts's Step. Kept in full so the step list can be copied across unchanged. */
interface Step {
  name: string;
  caption: string;
  /** Paths the next Browse clicks should answer with, in order. */
  dialogPaths?: string[];
  /** Playwright selectors clicked in order before the beat. */
  clicks?: string[];
  /** Selector that must be visible before the beat. A miss aborts the run. */
  expect?: string;
  /**
   * Keep whatever layer is open coming into this step.
   *
   * Steps normally start by pressing Escape, because a Radix menu left open by
   * one screen otherwise rides into the next, which on film scrims a whole
   * beat rather than costing one frame. A dialog the wizard raised on purpose,
   * though, is the thing the next step has to click, and Escape dismisses it
   * before the click lands. Beat 07 is that dialog, so this gate is the only
   * dismissal logic in the file: an unconditional per-beat Escape would cancel
   * the run before step 08 could start it.
   */
  keepOverlay?: boolean;
  /** Longer wait for this step's clicks and marker. Only the step that waits on the analyze raises it. */
  slowMs?: number;
  /**
   * Pixels to scroll the wizard body down before the beat.
   *
   * The review step is taller than the viewport. scrollIntoView does not work
   * here: the wizard body is its own scroll container, so it moves the page
   * around the container and the panel stays below the fold.
   */
  scrollBy?: number;
}

type Beat = { screen: string; hold: number; note: string };

/**
 * The narrative order, not the driving order. Sections 3 and 4 of the intro
 * video: the run as it came off the sequencer, what the barcodes said, the
 * verdict, replicate agreement, and finally the run's own health. The last beat
 * returns to a screen the wizard already passed, which is why the plan below
 * separates holding from driving.
 */
const TIMELINE: Beat[] = [
  { screen: "02-inputs-filled", hold: 4500, note: "run folder as it came off the sequencer" },
  { screen: "07-native-barcodes", hold: 3500, note: "barcodes detected" },
  { screen: "09-verdict-plate", hold: 6000, note: "288 wells, verdicts split" },
  { screen: "10-replicate-distribution", hold: 4000, note: "replicate agreement" },
  { screen: "08-run-quality", hold: 4000, note: "run health, nothing invented" },
];

/** Probe runs cut to the first two beats at a fixed short hold, which also stops short of the analyze. */
const PROBE_BEATS = 2;
const PROBE_HOLD = 1200;

function outputDir(): string {
  const flagIndex = process.argv.indexOf("--out");
  const relative = flagIndex >= 0 ? process.argv[flagIndex + 1] : "docs/.intro-video";
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
        `Recording now would film that server's build. ` +
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
  // Marked settled up front rather than dismissed per beat.
  await page.evaluate(() => {
    window.__store?.setState({ networkConsentGranted: true, networkConsentPending: false });
  });
  // AppLayout raises the EVOLVEpro round prompt whenever a campaign is loaded
  // with evolveproRound still 0 (AppLayout.tsx:94-97). MAME never loads variants
  // into the KURO store, so this has not been observed to fire here, but a modal
  // that appears once scrims a whole beat rather than costing one frame, and the
  // guard costs one round trip.
  await page.evaluate(() => {
    if (!window.__store) return;
    if ((window.__store.getState().evolveproRound ?? 0) === 0) {
      window.__store.setState({ evolveproRound: 1 });
    }
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
}

async function dismissOverlays(page: Page): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(120);
  }
}

/**
 * Run one wizard step. This is capture-mame.ts's runStep with the harvest pass
 * dropped: a recording run is never soft, because a miss films a screen that
 * contradicts its own subtitle.
 */
async function runStep(page: Page, step: Step): Promise<void> {
  const clickTimeout = step.slowMs ?? 15_000;
  const markerTimeout = step.slowMs ?? 20_000;
  if (step.dialogPaths) {
    const paths = step.dialogPaths;
    await page.evaluate((queued) => {
      window.__mockDialogQueue = { open: [...queued], save: [...queued] };
    }, paths);
  }

  for (const selector of step.clicks ?? []) {
    const target = page.locator(selector).first();
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
    if (!moved) throw new Error(`${step.name}: wizard body did not scroll`);
    await page.waitForTimeout(400);
  }

  if (step.expect) {
    await page.locator(step.expect).first().waitFor({ state: "visible", timeout: markerTimeout });
  }
  await page.waitForTimeout(600);
}

/**
 * Return to a step the wizard has already passed, by scroll alone.
 *
 * runStep cannot do this. Its scroll verifier asserts `scrollTop > 0`, so
 * scrolling back to the top of the same review page reads as a failure, and its
 * click loop would replay step 08's clicks and start a second analyze run.
 */
async function revisitStep(page: Page, step: Step): Promise<void> {
  const landed = await page.evaluate((amount) => {
    const body = document.querySelector('[data-testid="wizard-body"]');
    if (!body) return null;
    body.scrollTop = amount;
    return body.scrollTop;
  }, step.scrollBy ?? 0);
  if (landed === null) throw new Error(`${step.name}: wizard body not found on revisit`);
  if (landed !== (step.scrollBy ?? 0)) {
    throw new Error(`${step.name}: revisit scroll asked for ${step.scrollBy ?? 0}, landed on ${landed}`);
  }
  await page.waitForTimeout(400);

  if (step.expect) {
    await page.locator(step.expect).first().waitFor({ state: "visible", timeout: 20_000 });
  }
  await page.waitForTimeout(600);
}

/**
 * Copied unchanged from capture-mame.ts so both harnesses drive the same wizard.
 * Steps 11 and 12 (Janus, Activity) are omitted: no beat names them, and driving
 * past step 10 would leave the review screen the last two beats sit on.
 */
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
      caption: "Where output lands, and the draft placement the plate opens on.",
      scrollBy: 700,
    },
    {
      name: "04-parameters",
      caption: "The thresholds this run scores against.",
      scrollBy: 1800,
    },
    {
      name: "05-validated",
      caption: "Validation runs before any demux and reads the barcode sheet.",
      clicks: ['button:has-text("Validate")'],
      expect: "text=Validation complete",
      scrollBy: 1,
    },
    {
      name: "06-preflight",
      caption: "The pre-flight check every run passes through.",
      // The wizard footer button, not the "Run" menu in the menu bar. Only the
      // footer carries an aria-label, and a text match takes the menu first.
      clicks: ['button[aria-label="Run"]'],
      expect: "text=Pre-flight check",
    },
    {
      name: "07-native-barcodes",
      caption: "Three native barcodes carried this run, chosen as the replicate axis.",
      keepOverlay: true,
      clicks: ['button:has-text("Continue with warnings")'],
      expect: "text=Select the replicate axis for this run",
    },
    {
      name: "08-run-quality",
      caption: "What the run says about itself before a verdict is read.",
      keepOverlay: true,
      // :text-is, not :has-text. The latter is a case-insensitive substring
      // match, so "Run" also selects the dialog's "Cancel run" button, which
      // sits first in the DOM and silently abandons the run.
      //
      // The completion dialog is closed rather than filmed: it reports an
      // elapsed time measured against the recorded reply, and holding on that
      // would state a runtime nobody will see.
      clicks: ['[role="dialog"] button:text-is("Run")', 'button:text-is("Close")'],
      // The Close button arrives only when the analyze reply does, 83s later.
      slowMs: 600_000,
      expect: "text=Step 2.2",
    },
    {
      name: "09-verdict-plate",
      caption: "94 of 95 designed mutants recovered, on the plate and in the verdict table.",
      // 560, not capture-mame.ts's 900. That offset was calibrated against a
      // 1440x1120 viewport; this one is 40px shorter and the plate sits that
      // much further past the fold, so 900 filmed rows G and H alone with the
      // rest of the plate above the frame. 560 puts the "Plate map" heading at
      // the top of the wizard body, which is where the beat's subject starts.
      // Verified by pulling the mid-beat frame, not by reading the number.
      scrollBy: 560,
    },
    {
      name: "10-replicate-distribution",
      caption: "The same 288 verdicts as a per-plate distribution.",
      scrollBy: 1500,
    },
  ];
}

type Action =
  | { kind: "drive"; step: Step; beat?: Beat }
  | { kind: "revisit"; step: Step; beat: Beat };

/**
 * Bind each beat to its Step and work out how to reach it, before the browser
 * opens. A typo in TIMELINE would otherwise surface halfway through a recording
 * that has to be thrown away, and the beat list is the one part of this file a
 * person edits.
 *
 * Beats are held in TIMELINE order; steps are driven in wizard order. A beat
 * naming a screen the wizard has not reached yet is held where it falls, and a
 * beat naming one already passed becomes a revisit at the end.
 */
function buildPlan(steps: Step[], beats: Beat[]): Action[] {
  const names = steps.map((s) => s.name);
  const indexOf = (screen: string): number => {
    const at = names.indexOf(screen);
    if (at < 0) {
      throw new Error(
        `TIMELINE beat "${screen}" matches no wizard step. Known names: ${names.join(", ")}`,
      );
    }
    return at;
  };

  const last = Math.max(...beats.map((b) => indexOf(b.screen)));
  const actions: Action[] = [];
  let pending = 0;
  for (let i = 0; i <= last; i++) {
    const beat = pending < beats.length && beats[pending].screen === steps[i].name
      ? beats[pending++]
      : undefined;
    actions.push({ kind: "drive", step: steps[i], beat });
  }
  for (; pending < beats.length; pending++) {
    actions.push({ kind: "revisit", step: steps[indexOf(beats[pending].screen)], beat: beats[pending] });
  }
  return actions;
}

async function main(): Promise<void> {
  const dir = outputDir();
  const probe = process.argv.includes("--probe");
  if (!existsSync(BUNDLE_PATH)) {
    throw new Error(
      "scripts/mame-real-data.json missing. Run scripts/gen_mame_capture_data.py first.",
    );
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const bundle = createRequire(import.meta.url)("./mame-real-data.json") as MameBundle;
  mkdirSync(dir, { recursive: true });

  const beats = probe
    ? TIMELINE.slice(0, PROBE_BEATS).map((b) => ({ ...b, hold: PROBE_HOLD }))
    : TIMELINE;
  const plan = buildPlan(buildSteps(bundle), beats);

  const vite = await startVite();
  const browser = await chromium.launch({ headless: true });

  try {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 1,
      recordVideo: { dir, size: VIEWPORT },
    });
    const page = await context.newPage();
    const gaps: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      console.warn(`  [browser:error] ${text}`);
      if (text.includes("MOCK_MODE")) gaps.push(text);
    });

    // Recording begins with the page, so the clock the subtitles run against is
    // page creation and not the first beat. Everything before beat 1 (the
    // project picker, the tab switch, the wizard steps nobody films) is footage
    // the editor trims using the offsets below.
    const recordingStart = Date.now();
    await enterMame(page);

    let cumulative = 0;
    const entries: Array<Beat & { startMs: number; actualStartMs: number; actualEndMs: number }> = [];

    for (const action of plan) {
      const label = action.beat ? "record" : "drive";
      console.log(`[${label}] ${action.step.name}${action.beat ? ` (${action.beat.hold}ms)` : ""}`);

      if (action.kind === "drive") {
        if (!action.step.keepOverlay) await dismissOverlays(page);
        await runStep(page, action.step);
      } else {
        await dismissOverlays(page);
        await revisitStep(page, action.step);
      }

      if (!action.beat) continue;
      // The hold is the on-screen dwell only. Everything above is transition
      // time and is charged to actualStartMs rather than to the beat.
      const actualStartMs = Date.now() - recordingStart;
      await page.waitForTimeout(action.beat.hold);
      const actualEndMs = Date.now() - recordingStart;
      entries.push({
        screen: action.beat.screen,
        hold: action.beat.hold,
        note: action.beat.note,
        startMs: cumulative,
        actualStartMs,
        actualEndMs,
      });
      cumulative += action.beat.hold;
    }

    if (gaps.length > 0) {
      // Any MOCK_MODE text reaching the UI ends up in a status bar or banner and
      // rides into the footage, so the take is not publishable.
      throw new Error(`MOCK_MODE gaps reached the UI: ${[...new Set(gaps)].join(", ")}`);
    }

    // Playwright names the file from an internal hash and only finalises it on
    // close, so the path has to be taken from the live page first.
    const video = page.video();
    if (!video) throw new Error("recordVideo produced no video handle on the page");
    const rawPath = await video.path();

    await context.close();

    if (!existsSync(rawPath)) {
      throw new Error(`expected webm at ${rawPath} after context.close(), found nothing`);
    }
    const finalPath = resolve(dir, "mame-segment.webm");
    renameSync(rawPath, finalPath);

    writeFileSync(
      resolve(dir, "timeline-mame.json"),
      JSON.stringify(
        { video: "mame-segment.webm", probe, nominalDurationMs: cumulative, beats: entries },
        null,
        2,
      ) + "\n",
      "utf8",
    );
    console.log(`\n[record] ${entries.length} beats, ${cumulative}ms nominal -> ${finalPath}`);
  } finally {
    await browser.close();
    vite.kill("SIGTERM");
  }
}

main().catch((err) => {
  console.error("[record] failed:", err);
  process.exit(1);
});
