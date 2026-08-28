/**
 * record-motion.ts - the camera and hand for the intro-video recorders.
 *
 * scripts/record-intro.ts and scripts/record-intro-mame.ts used to hold each
 * beat with a bare waitForTimeout, which films a still. Everything here exists
 * to put movement inside that same window: a visible cursor that travels to the
 * thing it is about to press, containers that scroll rather than jump, and a
 * push-in onto the one number the subtitle is talking about.
 *
 * The cursor machinery is lifted from scripts/record-tutorial.ts (the SVG data
 * URL, the fixed-position div, the ripple) because that file already solved it.
 * The zoom is new.
 *
 * Assumptions, stated rather than discovered later:
 *  - #root exists and wraps the whole React tree (index.html:10, main.tsx:106).
 *  - Zoom is a CSS transform on #root, not `document.body.style.zoom`. A
 *    transform does not reflow, so a panel sized in viewport units cannot
 *    collapse under it, and Chromium re-rasterises the layer at the settled
 *    scale, so text stays sharp. `will-change` is deliberately NOT set: it pins
 *    the layer at its original raster scale and the push-in comes out blurry.
 *  - The cursor div lives on document.body, outside #root, so it is not scaled
 *    with the page and its coordinates stay in real viewport pixels, which is
 *    the same space page.mouse uses.
 *  - Radix portals also mount on document.body, so an open menu is not scaled.
 *    No beat zooms while a menu is open.
 */

import type { Page } from "playwright";

/** macOS arrow cursor, 24x24, verbatim from scripts/record-tutorial.ts. */
const CURSOR_SVG_DATA = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M4 2 L4 20 L8.5 15.5 L12 22 L14 21 L10.5 14.5 L17 14.5 Z' fill='white' stroke='black' stroke-width='1.5' stroke-linejoin='round'/%3E%3C/svg%3E`;

const CURSOR_ID = "__kuma_cursor";

/** Where an element can be found: first match, or first match containing text. */
export interface ElementSpec {
  selector: string;
  contains?: string;
}

export interface ZoomOptions {
  /** Fixed scale. Omit to fit the element into the frame with `padding`. */
  scale?: number;
  /** Push-in duration in ms. */
  ms?: number;
  /** Breathing room around the element when the scale is fitted, in CSS px. */
  padding?: number;
  /** Bounds on a fitted scale. A 1.0 floor keeps a wide panel from zooming out. */
  min?: number;
  max?: number;
}

export interface ZoomResult {
  scale: number;
  width: number;
  height: number;
  matched: string;
}

/* -------------------------------------------------------------- cursor */

/** Add the cursor to the page and park it. Safe to call twice. */
export async function injectCursor(page: Page, x = 960, y = 620): Promise<void> {
  await page.evaluate(
    ({ url, id, cx, cy }) => {
      document.getElementById(id)?.remove();
      const cursor = document.createElement("div");
      cursor.id = id;
      cursor.style.cssText = [
        "position: fixed",
        "z-index: 2147483647",
        "pointer-events: none",
        "width: 26px",
        "height: 26px",
        `background-image: url("${url}")`,
        "background-repeat: no-repeat",
        "background-size: contain",
        `left: ${cx}px`,
        `top: ${cy}px`,
        "filter: drop-shadow(0 2px 3px rgba(0,0,0,0.35))",
      ].join(";");
      document.body.appendChild(cursor);
    },
    { url: CURSOR_SVG_DATA, id: CURSOR_ID, cx: x, cy: y },
  );
  await page.mouse.move(x, y);
}

/**
 * Glide the cursor to (x, y) and take the real mouse with it.
 *
 * The CSS transition is written per move so the travel time scales with the
 * distance; a fixed 280ms makes a short hop look sluggish and a cross-screen
 * move look teleported. page.mouse.move is stepped so hover styles along the
 * path fire the way they would under a hand.
 */
export async function moveTo(page: Page, x: number, y: number, ms?: number): Promise<void> {
  const dist = await page.evaluate(
    ({ id, cx, cy }) => {
      const cursor = document.getElementById(id);
      if (!cursor) return 0;
      const dx = cx - parseFloat(cursor.style.left || "0");
      const dy = cy - parseFloat(cursor.style.top || "0");
      return Math.hypot(dx, dy);
    },
    { id: CURSOR_ID, cx: x, cy: y },
  );
  const travel = ms ?? Math.min(900, Math.max(260, Math.round(dist * 0.7)));
  await page.evaluate(
    ({ id, cx, cy, t }) => {
      const cursor = document.getElementById(id);
      if (!cursor) return;
      cursor.style.transition = `left ${t}ms cubic-bezier(0.33,0.9,0.25,1), top ${t}ms cubic-bezier(0.33,0.9,0.25,1)`;
      cursor.style.left = `${cx}px`;
      cursor.style.top = `${cy}px`;
    },
    { id: CURSOR_ID, cx: x, cy: y, t: travel },
  );
  await page.mouse.move(x, y, { steps: 12 });
  await page.waitForTimeout(travel + 40);
}

/** Blue pulse under the cursor, so a press is visible and not just implied. */
export async function showRipple(page: Page, x: number, y: number): Promise<void> {
  await page.evaluate(
    ({ cx, cy }) => {
      const ripple = document.createElement("div");
      ripple.style.cssText = [
        "position: fixed",
        "z-index: 2147483646",
        "pointer-events: none",
        `left: ${cx - 16}px`,
        `top: ${cy - 16}px`,
        "width: 32px",
        "height: 32px",
        "border-radius: 50%",
        "background: rgba(59,130,246,0.5)",
        "transform: scale(0)",
        "transition: transform 0.32s ease-out, opacity 0.32s ease-out",
        "opacity: 1",
      ].join(";");
      document.body.appendChild(ripple);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          ripple.style.transform = "scale(2.6)";
          ripple.style.opacity = "0";
          setTimeout(() => ripple.remove(), 420);
        }),
      );
    },
    { cx: x, cy: y },
  );
}

async function centerOf(page: Page, selector: string): Promise<{ x: number; y: number } | null> {
  try {
    const box = await page.locator(selector).first().boundingBox({ timeout: 4000 });
    if (!box || box.width < 1 || box.height < 1) return null;
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  } catch {
    return null;
  }
}

/** Travel to an element and stop there. Returns false when it is not on screen. */
export async function moveToSelector(page: Page, selector: string, ms?: number): Promise<boolean> {
  const c = await centerOf(page, selector);
  if (!c) return false;
  await moveTo(page, c.x, c.y, ms);
  return true;
}

/**
 * Travel to an element, pulse, then click it through real input.
 *
 * The click goes through the locator rather than page.mouse so Radix pointerdown
 * handlers see what they expect, which is the same reason the recorders never
 * used a JS .click().
 */
export async function clickSelector(page: Page, selector: string, timeout = 15_000): Promise<void> {
  const target = page.locator(selector).first();
  await target.waitFor({ state: "visible", timeout });
  const box = await target.boundingBox({ timeout });
  if (box) {
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await moveTo(page, x, y);
    await showRipple(page, x, y);
    await page.waitForTimeout(120);
  }
  await target.click({ timeout });
}

/** Rest the cursor on each element in turn, so hover states play on film. */
export async function hoverSequence(
  page: Page,
  selectors: string[],
  dwellMs = 420,
): Promise<number> {
  let hit = 0;
  for (const selector of selectors) {
    if (await moveToSelector(page, selector)) {
      hit += 1;
      await page.waitForTimeout(dwellMs);
    }
  }
  return hit;
}

/* -------------------------------------------------------------- scrolling */

const FIND_FN = `
  function __find(spec) {
    const nodes = Array.from(document.querySelectorAll(spec.selector));
    const visible = nodes.filter((n) => {
      const r = n.getBoundingClientRect();
      return r.width > 2 && r.height > 2;
    });
    const pool = visible.length > 0 ? visible : nodes;
    if (!spec.contains) return pool[0] || null;
    const needle = spec.contains.toLowerCase();
    const hits = pool.filter((n) => (n.textContent || "").toLowerCase().includes(needle));
    // Innermost wins. A broad selector otherwise resolves to whatever wrapper
    // happens to come first in the document, which for a zoom target means
    // framing the whole screen instead of the line the subtitle is about.
    const inner = hits.filter(
      (n) => !hits.some((m) => m !== n && n.contains(m)),
    );
    return inner[0] || hits[0] || null;
  }
  function __scroller(el) {
    let p = el.parentElement;
    while (p) {
      const s = getComputedStyle(p);
      if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight + 4) return p;
      p = p.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  }
`;

/**
 * Ease a scroll container so the element lands where `block` asks for.
 *
 * scrollIntoView is not usable here: several of these panels are their own
 * scroll container inside a taller one, and the browser moves the outer page
 * around the container while the panel stays below the fold. That is the same
 * trap the MAME recorder already documented for the wizard body.
 */
export async function smoothScrollIntoView(
  page: Page,
  spec: ElementSpec,
  opts: { ms?: number; block?: "center" | "start"; offset?: number } = {},
): Promise<boolean> {
  const ms = opts.ms ?? 1200;
  const block = opts.block ?? "center";
  const offset = opts.offset ?? 24;
  const ok = await page.evaluate(
    // eslint-disable-next-line no-new-func
    new Function(
      "args",
      `${FIND_FN}
      return new Promise((done) => {
        const el = __find(args.spec);
        if (!el) return done(false);
        const box = __scroller(el);
        const er = el.getBoundingClientRect();
        const br = box === (document.scrollingElement || document.documentElement)
          ? { top: 0, height: window.innerHeight }
          : box.getBoundingClientRect();
        const delta = args.block === "center"
          ? (er.top - br.top) - (br.height - er.height) / 2
          : (er.top - br.top) - args.offset;
        const from = box.scrollTop;
        const to = Math.max(0, Math.min(box.scrollHeight - box.clientHeight, from + delta));
        if (Math.abs(to - from) < 2) return done(true);
        const t0 = performance.now();
        const step = (t) => {
          const p = Math.min(1, (t - t0) / args.ms);
          const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
          box.scrollTop = from + (to - from) * e;
          if (p < 1) requestAnimationFrame(step); else done(true);
        };
        requestAnimationFrame(step);
      });`,
    ) as (args: unknown) => Promise<boolean>,
    { spec, ms, block, offset },
  );
  if (ok) await page.waitForTimeout(120);
  return ok;
}

/** Ease a named container to an absolute scrollTop. Used by the MAME wizard body. */
export async function smoothScrollTo(
  page: Page,
  selector: string,
  to: number,
  ms = 1200,
): Promise<boolean> {
  // Built from a string for the same reason smoothScrollIntoView is: tsx
  // compiles with esbuild's keepNames on, which rewrites a named inner function
  // into a __name(...) call. That helper does not exist in the page, and the
  // rewrite only bites when the animation branch is actually reached, so it
  // hides until a long scroll finally runs one.
  const ok = await page.evaluate(
    // eslint-disable-next-line no-new-func
    new Function(
      "args",
      `return new Promise(function (done) {
        var box = document.querySelector(args.sel);
        if (!box) return done(false);
        var from = box.scrollTop;
        var to2 = Math.max(0, Math.min(box.scrollHeight - box.clientHeight, args.target));
        if (Math.abs(to2 - from) < 2) { box.scrollTop = to2; return done(true); }
        var t0 = performance.now();
        requestAnimationFrame(function step(t) {
          var p = Math.min(1, (t - t0) / args.dur);
          var e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
          box.scrollTop = from + (to2 - from) * e;
          if (p < 1) requestAnimationFrame(step); else done(true);
        });
      });`,
    ) as (a: unknown) => Promise<boolean>,
    { sel: selector, target: to, dur: ms },
  );
  if (ok) await page.waitForTimeout(120);
  return ok;
}

/* -------------------------------------------------------------- zoom */

/**
 * Push in on an element by transforming #root.
 *
 * Measurement happens with the transform cleared, so a stale zoom cannot skew
 * the geometry. The translation is clamped to the frame, otherwise a panel near
 * an edge drags empty page background in beside it.
 */
export async function zoomTo(
  page: Page,
  specs: ElementSpec[],
  opts: ZoomOptions = {},
): Promise<ZoomResult | null> {
  const args = {
    specs,
    scale: opts.scale ?? 0,
    ms: opts.ms ?? 900,
    padding: opts.padding ?? 40,
    min: opts.min ?? 1.25,
    max: opts.max ?? 2.6,
  };
  const result = await page.evaluate(
    // eslint-disable-next-line no-new-func
    new Function(
      "args",
      `${FIND_FN}
      const root = document.getElementById("root");
      if (!root) return null;
      root.style.transition = "none";
      root.style.transform = "";
      root.style.transformOrigin = "0 0";
      void root.offsetWidth;
      let el = null; let matched = "";
      for (const spec of args.specs) {
        const found = __find(spec);
        if (found) {
          const r = found.getBoundingClientRect();
          if (r.width > 40 && r.height > 20) { el = found; matched = spec.selector + (spec.contains ? " ~ " + spec.contains : ""); break; }
        }
      }
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const vw = window.innerWidth, vh = window.innerHeight;
      let k = args.scale;
      if (!k) {
        k = Math.min(vw / (r.width + args.padding * 2), vh / (r.height + args.padding * 2));
      }
      k = Math.max(args.min, Math.min(args.max, k));
      const ex = r.left + r.width / 2, ey = r.top + r.height / 2;
      let tx = vw / 2 - k * ex, ty = vh / 2 - k * ey;
      tx = Math.min(0, Math.max(vw - k * vw, tx));
      ty = Math.min(0, Math.max(vh - k * vh, ty));
      requestAnimationFrame(() => {
        root.style.transition = "transform " + args.ms + "ms cubic-bezier(0.32,0.72,0.3,1)";
        root.style.transform = "translate(" + tx + "px, " + ty + "px) scale(" + k + ")";
      });
      return { scale: k, width: r.width, height: r.height, matched: matched };`,
    ) as (a: unknown) => ZoomResult | null,
    args,
  );
  if (result) await page.waitForTimeout(args.ms + 220);
  return result;
}

/** Drop the zoom. `ms` of 0 cuts, anything else eases back out. */
export async function resetZoom(page: Page, ms = 0): Promise<void> {
  await page.evaluate(
    ({ dur }) => {
      const root = document.getElementById("root");
      if (!root) return;
      if (dur > 0) {
        root.style.transition = `transform ${dur}ms cubic-bezier(0.32,0.72,0.3,1)`;
        root.style.transform = "translate(0px, 0px) scale(1)";
      } else {
        root.style.transition = "none";
        root.style.transform = "";
      }
    },
    { dur: ms },
  );
  await page.waitForTimeout(ms > 0 ? ms + 120 : 60);
}

/** Sleep helper so beat scripts read as a sequence of moves. */
export async function dwell(page: Page, ms: number): Promise<void> {
  if (ms > 0) await page.waitForTimeout(ms);
}
