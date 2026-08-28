/**
 * KURO intro video segment, recorded from the running dev build.
 *
 * This is capture-real.ts with the screenshot loop replaced by a timeline: the
 * same store states drive the same real build, but instead of taking one frame
 * per screen the run dwells on each beat for a fixed time while Playwright
 * records the page to webm. Everything the viewer sees is the actual UI holding
 * values the sidecar computed, which is the whole point of reusing the real
 * data bundle rather than filming a mock.
 *
 * Kept verbatim from capture-real.ts because the failure modes are identical:
 *   - the run refuses to start when port 1421 is already taken, so a stale
 *     server cannot silently supply a different build
 *   - Vite is spawned without a shell, so the kill reaches the node process
 *   - the consent modal is settled and overlays are dismissed between beats,
 *     otherwise one screen's dropdown rides into the next one on film
 *   - MOCK_MODE text reaching the UI fails the run
 *
 * Usage:
 *   pnpm exec tsx scripts/record-intro.ts [--probe] [--out docs/.intro-video]
 */

import { chromium, type Page } from "playwright";
import { spawn, execFileSync, type ChildProcess } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { mkdirSync, existsSync, writeFileSync, renameSync } from "fs";
import { createRequire } from "module";
import { screenStates, type ScreenState } from "./real-data.js";
import {
  injectCursor,
  moveTo,
  moveToSelector,
  smoothScrollIntoView,
  smoothScrollTo,
  zoomTo,
  resetZoom,
  dwell,
} from "./record-motion.js";

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
/** Native 1080p. deviceScaleFactor stays 1: a 2x buffer only inflates the file. */
const VIEWPORT = { width: 1920, height: 1080 };

/**
 * A beat is a held shot, and `motion` is what happens inside it.
 *
 * Without `motion` the hold is a waitForTimeout and the beat films a still,
 * which is what the first cut of this video was: eight screens averaging 5.1
 * seconds each, no cursor, no scroll, nothing for the eye to follow. The
 * motion runs inside the same window the assembler cuts (actualStartMs plus
 * `hold`), so anything it does is on film; anything before applyState returns
 * is transition footage and gets trimmed.
 */
type Beat = {
  screen: string;
  hold: number;
  note: string;
  motion?: (page: Page) => Promise<void>;
};

/** Names the rescue pass recovered, read from the same bundle the states come from. */
const rescuedNames: string[] = (() => {
  const bundle = createRequire(import.meta.url)("./real-data.json") as {
    design: { rescued_mutations?: Array<string | { original: string }> };
  };
  return (bundle.design.rescued_mutations ?? []).map((e) =>
    typeof e === "string" ? e : e.original,
  );
})();

/** Selector for the pane holding the primer table on the output step. */
const PRIMER_PANEL = '[data-testid="output-primer-panel"]';
const INSPECTOR = '[data-testid="inspector"]';
const PLATE_PANEL = '[data-testid="output-plate-panel"]';

/** Sweep the cursor across a handful of points inside an element's box. */
async function sweepAcross(
  page: Page,
  selector: string,
  points: Array<[number, number]>,
  dwellMs = 380,
): Promise<boolean> {
  const box = await page.locator(selector).first().boundingBox({ timeout: 5000 }).catch(() => null);
  if (!box) return false;
  for (const [fx, fy] of points) {
    await moveTo(page, box.x + box.width * fx, box.y + box.height * fy);
    await page.waitForTimeout(dwellMs);
  }
  return true;
}

/**
 * Walk the progress bar the way the sidecar drives it.
 *
 * The 10-designing state is a snapshot of a run in flight, so holding it still
 * films a frozen progress bar. Stepping `progress` and the status line moves it
 * without inventing anything: the ceiling is the run's own 95 designed
 * primers, which is what the finished state reports.
 */
async function animateDesignProgress(page: Page, totalMs: number): Promise<void> {
  const steps = [18, 31, 44, 57, 68, 79, 88, 94];
  const per = Math.max(120, Math.floor(totalMs / steps.length));
  for (const pct of steps) {
    await page.evaluate(
      ({ p, done, total }) => {
        window.__store?.setState({
          progress: p,
          isDesigning: true,
          statusMessage: `Designing primers... (${done}/${total})`,
        });
      },
      { p: pct, done: Math.round((pct / 100) * 95), total: 95 },
    );
    await page.waitForTimeout(per);
  }
}

/**
 * The narrative order, not the capture order. It walks one story (load, predict,
 * design, rescue, report, plate, export) and deliberately skips the screens that
 * exist only to document a control.
 */
const TIMELINE: Beat[] = [
  {
    screen: "02-file-loaded",
    hold: 8000,
    note: "plasmid loaded",
    motion: async (page) => {
      await moveToSelector(page, "select");
      await dwell(page, 400);
      await sweepAcross(page, "svg, canvas", [
        [0.25, 0.5],
        [0.7, 0.5],
      ], 300);
      // The sidecar log line carries the plasmid and the 561 residues the
      // subtitle names. The Source Inspector does not: on this step it still
      // reads "No artifact loaded", which is why it is not the target.
      await zoomTo(page, [{ selector: "div, span, p", contains: "561 aa" }], {
        ms: 1100,
        min: 1.4,
        max: 1.9,
        padding: 420,
      });
      await dwell(page, 900);
    },
  },
  {
    screen: "03-mutations-entered",
    hold: 6000,
    note: "10,528 predictions in",
    motion: async (page) => {
      // EVOLVEpro mode has no textarea: the variants arrive as a CSV and the
      // step shows a banner plus the column mapping, so the travel is the
      // wizard body and the target is the banner stating the count.
      await moveToSelector(page, "button:has-text('Preview'), select");
      // Zoom the count first, then pull back and travel down to the ranked
      // predictions it came from. Scrolling first put the banner above the
      // fold and left the zoom with nothing to frame.
      await zoomTo(page, [{ selector: "div, span, p", contains: "variants loaded" }], {
        ms: 900,
        min: 1.4,
        max: 1.9,
        padding: 420,
      });
      await dwell(page, 900);
      await resetZoom(page, 600);
      await smoothScrollTo(page, '[data-testid="wizard-body"]', 320, 1200);
      await dwell(page, 400);
    },
  },
  {
    screen: "10-designing",
    hold: 5000,
    note: "design running",
    // The one beat whose motion is the app's own state rather than the camera.
    motion: async (page) => {
      await animateDesignProgress(page, 4200);
    },
  },
  {
    screen: "04-design-complete",
    hold: 6500,
    note: "95/95 designed",
    motion: async (page) => {
      await sweepAcross(page, PRIMER_PANEL, [
        [0.3, 0.35],
        [0.6, 0.5],
      ]);
      await zoomTo(page, [{ selector: INSPECTOR }], { ms: 1100, min: 1.5, max: 2.1 });
      await dwell(page, 1400);
    },
  },
  {
    screen: "11-rescued-rows",
    hold: 8000,
    note: "auto-relax rescues",
    motion: async (page) => {
      // The state's own action already parked the row mid-table. Ride back up
      // and travel down to it, so the arrival is a scroll rather than a cut.
      await smoothScrollTo(page, PRIMER_PANEL, 0, 700);
      const rows = rescuedNames.slice(0, 3);
      for (const name of rows) {
        await smoothScrollIntoView(page, { selector: "tr", contains: name }, { ms: 900 });
        await moveToSelector(page, "tr:has-text('" + name + "')");
        await dwell(page, 450);
      }
      if (rows.length > 0) {
        await zoomTo(page, [{ selector: "tr", contains: rows[0] }, { selector: PRIMER_PANEL }], {
          ms: 1000,
          min: 1.6,
          max: 2.4,
          padding: 220,
        });
        await dwell(page, 1200);
      }
    },
  },
  {
    screen: "16-design-report",
    hold: 8000,
    note: "design report",
    motion: async (page) => {
      await zoomTo(page, [{ selector: INSPECTOR }], { ms: 1000, min: 1.5, max: 2.0 });
      await dwell(page, 700);
      // Travel the report inside the zoom: rescue block first, then the Tm
      // distribution the subtitle names.
      await smoothScrollIntoView(page, { selector: "h4", contains: "Rescue" }, { ms: 1200 });
      await dwell(page, 900);
      await smoothScrollIntoView(page, { selector: "h4", contains: "Tm" }, { ms: 1400 });
      // Tighter than beat 04's framing of the same inspector, so the two beats
      // do not read as the same shot held twice.
      await zoomTo(page, [{ selector: "div", contains: "Overlap" }, { selector: INSPECTOR }], {
        ms: 800,
        min: 1.8,
        max: 2.4,
        padding: 260,
      });
      await dwell(page, 700);
    },
  },
  {
    screen: "05-plate-map",
    hold: 5000,
    note: "96-well plate",
    motion: async (page) => {
      await sweepAcross(
        page,
        PLATE_PANEL,
        [
          [0.2, 0.35],
          [0.5, 0.55],
          [0.78, 0.4],
          [0.4, 0.75],
        ],
        420,
      );
      await zoomTo(page, [{ selector: PLATE_PANEL }], { ms: 900, min: 1.25, max: 1.7 });
      await dwell(page, 600);
    },
  },
  {
    screen: "17-mapping-export",
    hold: 8500,
    note: "export, MAME handoff",
    motion: async (page) => {
      await moveToSelector(page, "select#amount, select");
      await dwell(page, 400);
      await moveToSelector(page, INSPECTOR);
      await zoomTo(page, [{ selector: INSPECTOR }], { ms: 1100, min: 1.6, max: 2.2 });
      await dwell(page, 1200);
      await smoothScrollIntoView(page, { selector: INSPECTOR, contains: "MAME" }, { ms: 1300 });
      await dwell(page, 1600);
    },
  },
];

/** Probe runs cut to the first three beats at a fixed short hold. */
const PROBE_BEATS = 3;
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
 * UniProt, InterPro or the benchmark. Once open it covers every later screen.
 * The lookups are already resolved offline into real-data.json, so the run
 * marks consent as settled and keeps it settled between beats.
 */
async function settleConsent(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (!window.__store) return;
    window.__store.setState({ networkConsentGranted: true, networkConsentPending: false });
  });
}

/**
 * AppLayout raises the round prompt whenever an EVOLVEpro campaign is loaded
 * with evolveproRound still 0 (AppLayout.tsx:94-97), which every beat after the
 * variants land satisfies. dismissOverlays cannot help: it runs before the state
 * that opens the modal. In a screenshot set that costs one frame, on film it
 * scrims a whole beat, so the round is set to 1 before the state lands. No entry
 * in screenStates writes evolveproRound, so nothing here is being overridden.
 */
async function settleRoundPrompt(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (!window.__store) return;
    if ((window.__store.getState().evolveproRound ?? 0) === 0) {
      window.__store.setState({ evolveproRound: 1 });
    }
  });
}

/**
 * A Radix dropdown opened for one screen stays open into the next one. On film
 * that is worse than in a screenshot set: the stale layer is visible for the
 * whole of the following beat.
 */
async function dismissOverlays(page: Page): Promise<void> {
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(120);
  }
}

async function applyState(page: Page, screen: ScreenState): Promise<void> {
  // Every beat starts from an unzoomed frame. zoomTo measures with the
  // transform cleared, so a leftover push-in would not corrupt the geometry,
  // but it would corrupt the shot.
  await resetZoom(page);
  await dismissOverlays(page);
  await settleConsent(page);
  await settleRoundPrompt(page);
  await page.evaluate(
    ({ state, nav }) => {
      if (!window.__store) throw new Error("window.__store missing; is MOCK_MODE dev build running?");
      window.__store.setState({ ...state, ...(nav ?? {}) });
    },
    { state: screen.state, nav: screen.nav ?? null },
  );
  // Dialogs behind React.lazy need a beat to fetch their chunk before the hold.
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
    // A miss here films a screen that contradicts its own subtitle, so it is a
    // hard failure rather than a warning.
    const hit = await page.evaluate<boolean>(`(async () => { ${screen.action} })()`);
    if (hit === false) {
      throw new Error(`${screen.name}: action matched no element`);
    }
    await page.waitForTimeout(500);
  }
}

/**
 * Bind each beat to its ScreenState now rather than inside the loop. A typo in
 * TIMELINE would otherwise surface halfway through a recording that has to be
 * thrown away, and the beat list is the one part of this file a person edits.
 */
function resolveTimeline(probe: boolean): Array<Beat & { state: ScreenState }> {
  const beats = probe
    ? TIMELINE.slice(0, PROBE_BEATS).map((b) => ({ ...b, hold: PROBE_HOLD }))
    : TIMELINE;
  return beats.map((beat) => {
    const state = screenStates.find((s) => s.name === beat.screen);
    if (!state) {
      throw new Error(
        `TIMELINE beat "${beat.screen}" matches no screenStates entry. ` +
          `Known names: ${screenStates.map((s) => s.name).join(", ")}`,
      );
    }
    return { ...beat, state };
  });
}

async function main(): Promise<void> {
  const dir = outputDir();
  const probe = process.argv.includes("--probe");
  if (!existsSync(resolve(ROOT, "scripts/real-data.json"))) {
    throw new Error("scripts/real-data.json missing. Run scripts/gen_real_capture_data.py first.");
  }
  mkdirSync(dir, { recursive: true });

  const beats = resolveTimeline(probe);
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
    // project picker click) is footage the editor trims.
    const recordingStart = Date.now();
    await enterWorkspace(page);
    // The cursor lives on document.body, so a React re-render cannot take it
    // away and it survives every setState the beats do.
    await injectCursor(page);

    let cumulative = 0;
    const entries: Array<
      Beat & { startMs: number; actualStartMs: number; actualEndMs: number }
    > = [];

    for (const beat of beats) {
      console.log(`[record] ${beat.screen} (${beat.hold}ms)`);
      await applyState(page, beat.state);
      // The hold is the on-screen dwell only. Setup above is transition time and
      // is charged to actualStartMs rather than to the beat.
      const actualStartMs = Date.now() - recordingStart;
      if (beat.motion) {
        const t0 = Date.now();
        await beat.motion(page);
        const spent = Date.now() - t0;
        if (spent > beat.hold) {
          // The assembler caps the cut at the nominal hold, so an overrun is
          // footage that gets thrown away mid-move. Worth knowing about.
          console.warn(
            `  [motion] ${beat.screen} ran ${spent}ms against a ${beat.hold}ms hold; the tail will be cut`,
          );
        }
        await page.waitForTimeout(Math.max(0, beat.hold - spent));
      } else {
        await page.waitForTimeout(beat.hold);
      }
      const actualEndMs = Date.now() - recordingStart;
      entries.push({
        screen: beat.screen,
        hold: beat.hold,
        note: beat.note,
        startMs: cumulative,
        actualStartMs,
        actualEndMs,
      });
      cumulative += beat.hold;
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
    const finalPath = resolve(dir, "kuro-segment.webm");
    renameSync(rawPath, finalPath);

    writeFileSync(
      resolve(dir, "timeline.json"),
      JSON.stringify(
        { video: "kuro-segment.webm", probe, nominalDurationMs: cumulative, beats: entries },
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
