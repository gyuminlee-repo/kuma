/**
 * kuma intro video, hook segment. Three cuts of the raw campaign files that
 * exist before the app is opened at all, so the segment answers "what is the
 * operator actually holding" before any UI appears.
 *
 * Unlike record-intro.ts this never starts Vite and never touches port 1421.
 * It builds one local HTML page with three full-viewport sections and films
 * that page, because the subject is the data on disk rather than the product.
 *
 * The Playwright mechanics are lifted verbatim from record-intro.ts, since the
 * failure modes are the same: recordVideo is bound to the context, the file is
 * only finalised on close, and video.path() has to be taken from the live page
 * before that close.
 *
 * Every number on screen is computed from the files below at run time. The
 * fastq count in particular is asserted, because a wrong figure (288, which is
 * the well count and not a file count) is circulating in older notes.
 *
 * Usage:
 *   node node_modules/.bin/tsx scripts/record-intro-hook.ts [--probe] [--out docs/.intro-video]
 */

import { chromium } from "playwright";
import { execFileSync } from "child_process";
import { resolve, dirname, join, basename } from "path";
import { homedir, tmpdir } from "os";
import { fileURLToPath } from "url";
import { mkdirSync, mkdtempSync, existsSync, writeFileSync, renameSync, copyFileSync, readFileSync, readdirSync, statSync } from "fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

/**
 * Sources. These are lab campaign files rather than repo fixtures, so they live
 * outside the checkout and are resolved from the workspace root instead of
 * being written out literally. Override WORKSPACE_ROOT to film another copy.
 */
const WORKSPACE = process.env.WORKSPACE_ROOT ?? join(homedir(), "_workspace");
/** EVOLVEpro round-1 prediction table handed to KURO. */
const CSV_PATH = join(WORKSPACE, "999.kuma_record_input", "df_test.csv");
/** MAME test bundle: plate order workbook plus the run it produced. */
const MAME_TEST = join(WORKSPACE, "260730 MAME test");
/** Plate order workbook sent to the oligo vendor; "Fwd List" is the order sheet. */
const XLSX_PATH = join(MAME_TEST, "260722_Ep_R2-1_platemap_plate-order.xlsx");
const XLSX_SHEET = "Fwd List";
/** MinKNOW run folder returned by the sequencer for that plate. */
const RUN_DIR = join(MAME_TEST, "260729_KHM", "20260729_1904_X4_FBF91250_f497f4eb");
/** Python that carries openpyxl. The repo venv is the primary, python3 the fallback. */
const VENV_PYTHON = join(ROOT, "..", "..", "..", ".venv", "bin", "python");

/** Native 1080p, matching record-intro.ts. A 2x buffer only inflates the file. */
const VIEWPORT = { width: 1920, height: 1080 };
const HOLD_MS = 10_000;
const PROBE_HOLD_MS = 2_000;

/** Rows rendered for cut 1. The table is not meant to be read to its end. */
const CSV_RENDER_ROWS = 300;
/** Columns of the order sheet that a person actually orders against. */
const FWD_COLUMNS = ["Well", "Primer Name", "Sequence", "Length", "Tm", "Mutation"];
/** Guard against filming the wrong run folder. Counted by hand from this run. */
const EXPECTED_FASTQ_FILES = 57;

type Cut = { cut: number; source: string; label: string };

const CUTS: Cut[] = [
  { cut: 1, source: CSV_PATH, label: "EVOLVEpro predictions" },
  { cut: 2, source: `${XLSX_PATH} [${XLSX_SHEET}]`, label: "plate order sheet" },
  { cut: 3, source: RUN_DIR, label: "MinKNOW run folder" },
];

function outputDir(): string {
  const flagIndex = process.argv.indexOf("--out");
  const relative = flagIndex >= 0 ? process.argv[flagIndex + 1] : "docs/.intro-video";
  return resolve(ROOT, relative);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* ------------------------------------------------------------------ cut 1 */

type CsvData = { header: string[]; rows: string[][]; totalRows: number };

function readCsv(): CsvData {
  // The file is plain comma separated with no quoted fields, so a split is
  // enough and pulling in a parser would only add a dependency.
  const lines = readFileSync(CSV_PATH, "utf8").split("\n").filter((l) => l.length > 0);
  const header = lines[0].split(",").map((h) => (h === "" ? "#" : h));
  const body = lines.slice(1);
  return {
    header,
    rows: body.slice(0, CSV_RENDER_ROWS).map((l) => l.split(",")),
    totalRows: body.length,
  };
}

/* ------------------------------------------------------------------ cut 2 */

type SheetData = { header: string[]; rows: string[][]; totalRows: number };

function pythonBinary(): string {
  const candidates = [VENV_PYTHON, "python3"];
  for (const candidate of candidates) {
    try {
      execFileSync(candidate, ["-c", "import openpyxl"], { stdio: "ignore" });
      return candidate;
    } catch {
      // Next candidate. A total miss is reported by the caller.
    }
  }
  throw new Error(
    `no python with openpyxl found. Tried: ${candidates.join(", ")}. ` +
      `Install it, or point VENV_PYTHON at an interpreter that has it.`,
  );
}

function readSheet(): SheetData {
  const script = [
    "import json, sys, openpyxl",
    "wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)",
    "ws = wb[sys.argv[2]]",
    "rows = [list(r) for r in ws.iter_rows(values_only=True)]",
    "print(json.dumps(rows, default=str))",
  ].join("\n");
  const raw = execFileSync(pythonBinary(), ["-c", script, XLSX_PATH, XLSX_SHEET], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  const table = JSON.parse(raw) as Array<Array<string | null>>;
  const sheetHeader = table[0].map((c) => String(c ?? ""));
  const keep = FWD_COLUMNS.map((name) => {
    const index = sheetHeader.indexOf(name);
    if (index < 0) {
      throw new Error(`column "${name}" is not in ${XLSX_SHEET}: ${sheetHeader.join(", ")}`);
    }
    return index;
  });
  const body = table.slice(1).filter((r) => r.some((c) => c !== null && c !== ""));
  return {
    header: FWD_COLUMNS,
    rows: body.map((r) => keep.map((i) => String(r[i] ?? ""))),
    totalRows: body.length,
  };
}

/* ------------------------------------------------------------------ cut 3 */

type TreeLine = { text: string; kind: "root" | "dir" | "file" };
type RunData = { lines: TreeLine[]; fastqFiles: number; barcodes: number };

function readRun(): RunData {
  const lines: TreeLine[] = [{ text: `${basename(RUN_DIR)}/`, kind: "root" }];
  const fastqPass = join(RUN_DIR, "fastq_pass");
  const barcodeDirs = readdirSync(fastqPass)
    .filter((n) => statSync(join(fastqPass, n)).isDirectory())
    .sort();

  let fastqFiles = 0;
  lines.push({ text: "|-- fastq_pass/", kind: "dir" });
  barcodeDirs.forEach((bc, bcIndex) => {
    const files = readdirSync(join(fastqPass, bc))
      .filter((n) => !n.startsWith("."))
      .sort();
    fastqFiles += files.length;
    const lastDir = bcIndex === barcodeDirs.length - 1;
    const dirElbow = lastDir ? "`--" : "|--";
    lines.push({
      text: `|   ${dirElbow} ${bc}/  (${files.length} file${files.length === 1 ? "" : "s"})`,
      kind: "dir",
    });
    files.forEach((file, fileIndex) => {
      const spine = lastDir ? "    " : "|   ";
      const elbow = fileIndex === files.length - 1 ? "`--" : "|--";
      lines.push({ text: `|   ${spine}${elbow} ${file}`, kind: "file" });
    });
  });

  // Run-level files sit beside fastq_pass and are what MAME reads for metadata,
  // QC and flow cell identity, so they belong in the same shot.
  const topEntries = readdirSync(RUN_DIR)
    .filter((n) => !n.startsWith("."))
    .sort();
  const topDirs = topEntries.filter(
    (n) => n !== "fastq_pass" && statSync(join(RUN_DIR, n)).isDirectory(),
  );
  const topFiles = topEntries.filter((n) => !statSync(join(RUN_DIR, n)).isDirectory());
  const tail = [...topDirs.map((n) => `${n}/`), ...topFiles];
  tail.forEach((name, index) => {
    const elbow = index === tail.length - 1 ? "`--" : "|--";
    lines.push({ text: `${elbow} ${name}`, kind: name.endsWith("/") ? "dir" : "file" });
  });

  return { lines, fastqFiles, barcodes: barcodeDirs.length };
}

/* -------------------------------------------------------------------- page */

function tableHtml(header: string[], rows: string[][]): string {
  const head = header.map((h) => `<th>${escapeHtml(h)}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`)
    .join("\n");
  return `<table><thead><tr>${head}</tr></thead><tbody>\n${body}\n</tbody></table>`;
}

function buildHtml(csv: CsvData, sheet: SheetData, run: RunData): string {
  const csvMeta = `${csv.totalRows.toLocaleString("en-US")} rows, ${csv.header.length} columns`;
  const sheetMeta = `${sheet.totalRows} primers, ${sheet.header.length} of 9 columns shown`;
  const runMeta = `${run.fastqFiles} fastq.gz files across ${run.barcodes} barcode folders`;

  const treeHtml = run.lines
    .map((l, i) => `<div class="tree-line ${l.kind}" data-i="${i}">${escapeHtml(l.text)}</div>`)
    .join("\n");

  return `<meta charset="utf-8">
<title>kuma intro hook</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; width: 1920px; height: 1080px; overflow: hidden;
    background: #0b0e14; color: #d5dae3;
    font-family: "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace;
  }
  section { display: none; width: 1920px; height: 1080px; flex-direction: column; }
  section.active { display: flex; }
  header {
    flex: 0 0 auto; padding: 20px 40px 16px; border-bottom: 1px solid #232936;
    background: #0b0e14;
  }
  .path { font-size: 25px; color: #e8edf5; letter-spacing: 0.2px; }
  .meta { font-size: 21px; color: #7f8ba0; margin-top: 6px; }
  .meta b { color: #8fd6a0; font-weight: 600; }
  .scroll { flex: 1 1 auto; overflow: hidden; padding: 0 40px; }
  table { border-collapse: collapse; font-size: 23px; line-height: 34px; }
  th, td { padding: 0 22px 0 0; text-align: left; white-space: nowrap; }
  thead th {
    color: #6fb3ff; border-bottom: 1px solid #2b3242; padding-bottom: 6px;
    position: sticky; top: 0; background: #0b0e14;
  }
  tbody td { color: #b9c2d0; }
  tbody td:first-child { color: #6c7789; }
  tbody tr:nth-child(even) td { background: #0f131c; }
  .tree { font-size: 24px; line-height: 36px; padding-top: 10px; }
  .tree-line { white-space: pre; opacity: 0; color: #b9c2d0; }
  .tree-line.shown { opacity: 1; }
  .tree-line.root { color: #e8edf5; }
  .tree-line.dir { color: #6fb3ff; }
</style>

<section id="cut-1">
  <header>
    <div class="path">${escapeHtml(CSV_PATH)}</div>
    <div class="meta"><b>${escapeHtml(csvMeta)}</b> &middot; EVOLVEpro round 1 predictions</div>
  </header>
  <div class="scroll" id="scroll-1">${tableHtml(csv.header, csv.rows)}</div>
</section>

<section id="cut-2">
  <header>
    <div class="path">${escapeHtml(basename(XLSX_PATH))} &nbsp;&rsaquo;&nbsp; ${escapeHtml(XLSX_SHEET)}</div>
    <div class="meta"><b>${escapeHtml(sheetMeta)}</b> &middot; oligo order for one 96 well plate</div>
  </header>
  <div class="scroll" id="scroll-2">${tableHtml(sheet.header, sheet.rows)}</div>
</section>

<section id="cut-3">
  <header>
    <div class="path">${escapeHtml(RUN_DIR)}</div>
    <div class="meta"><b>${escapeHtml(runMeta)}</b> &middot; MinKNOW output, one sequencing run</div>
  </header>
  <div class="scroll" id="scroll-3"><div class="tree">${treeHtml}</div></div>
</section>

<script>
  window.__showCut = function (n) {
    document.querySelectorAll('section').forEach(function (s) { s.classList.remove('active'); });
    document.getElementById('cut-' + n).classList.add('active');
    var scroll = document.getElementById('scroll-' + n);
    scroll.scrollTop = 0;
    if (n === 3) {
      document.querySelectorAll('.tree-line').forEach(function (l) { l.classList.remove('shown'); });
    }
  };

  // Scroll and reveal are driven by rAF against wall clock rather than by a
  // fixed step per frame, so a dropped frame shifts nothing: position is always
  // a function of elapsed time and the take stays on its 10 second budget.
  function animateScroll(el, durationMs, holdStartMs, distance) {
    var t0 = performance.now();
    function frame(now) {
      var t = now - t0;
      var p = Math.min(1, Math.max(0, (t - holdStartMs) / (durationMs - holdStartMs)));
      el.scrollTop = distance * p;
      if (t < durationMs) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  window.__runCut1 = function (durationMs) {
    var el = document.getElementById('scroll-1');
    // Deliberately short of the rendered bottom: the table has to look like it
    // keeps going, which is what the real file does for another 10,000 rows.
    var distance = Math.min(el.scrollHeight - el.clientHeight, 8000);
    animateScroll(el, durationMs, 400, distance);
  };

  window.__runCut2 = function (durationMs) {
    var el = document.getElementById('scroll-2');
    // Settle on the first wells before moving, then walk the whole plate.
    animateScroll(el, durationMs, 1800, el.scrollHeight - el.clientHeight);
  };

  window.__runCut3 = function (durationMs) {
    var el = document.getElementById('scroll-3');
    var lines = Array.prototype.slice.call(document.querySelectorAll('.tree-line'));
    var t0 = performance.now();
    function frame(now) {
      var p = Math.min(1, (now - t0) / durationMs);
      var visible = Math.max(1, Math.round(lines.length * p));
      for (var i = 0; i < visible; i++) { lines[i].classList.add('shown'); }
      var last = lines[visible - 1];
      // Keep the newest line near the bottom of the frame so the reveal reads
      // as the tree growing downward rather than as a jump.
      var target = last.offsetTop + last.offsetHeight - el.clientHeight + 60;
      el.scrollTop = Math.max(0, target);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  };
</script>
`;
}

/* -------------------------------------------------------------------- main */

async function main(): Promise<void> {
  const dir = outputDir();
  const probe = process.argv.includes("--probe");
  const hold = probe ? PROBE_HOLD_MS : HOLD_MS;
  mkdirSync(dir, { recursive: true });

  const csv = readCsv();
  const sheet = readSheet();
  const run = readRun();

  if (run.fastqFiles !== EXPECTED_FASTQ_FILES) {
    throw new Error(
      `fastq_pass holds ${run.fastqFiles} files, expected ${EXPECTED_FASTQ_FILES}. ` +
        `Either RUN_DIR points at a different run or the folder changed. ` +
        `Filming a wrong count is the one thing this cut must not do.`,
    );
  }
  console.log(
    `[hook] csv ${csv.totalRows} rows, sheet ${sheet.totalRows} primers, ` +
      `run ${run.fastqFiles} fastq files in ${run.barcodes} barcodes, ${run.lines.length} tree lines`,
  );

  // The page and the raw recording live in a private scratch dir rather than in
  // the output dir. The output dir is shared with the other intro recorders,
  // and a run of one of those clears it: a take that recorded straight into it
  // lost its webm between video.path() and context.close(). Only the finished
  // files are placed in the output dir, at the end.
  const scratch = mkdtempSync(join(tmpdir(), "kuma-hook-"));
  const pagePath = resolve(scratch, "hook-page.html");
  writeFileSync(pagePath, buildHtml(csv, sheet, run), "utf8");
  if (readFileSync(pagePath, "utf8").includes("\u2014")) {
    throw new Error("generated HTML contains an em dash");
  }

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 1,
      recordVideo: { dir: scratch, size: VIEWPORT },
    });
    const page = await context.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") console.warn(`  [browser:error] ${msg.text()}`);
    });

    const recordingStart = Date.now();
    await page.goto(`file://${pagePath}`, { waitUntil: "load" });

    const entries: Array<Cut & { startMs: number; actualStartMs: number; actualEndMs: number }> = [];
    let cumulative = 0;

    for (const cut of CUTS) {
      console.log(`[hook] cut ${cut.cut} (${hold}ms)`);
      await page.evaluate((n) => {
        (window as unknown as Record<string, (v: number) => void>).__showCut(n);
      }, cut.cut);
      const actualStartMs = Date.now() - recordingStart;
      await page.evaluate(
        ({ n, d }) => {
          (window as unknown as Record<string, (v: number) => void>)[`__runCut${n}`](d);
        },
        { n: cut.cut, d: hold },
      );
      await page.waitForTimeout(hold);
      const actualEndMs = Date.now() - recordingStart;
      entries.push({ ...cut, startMs: cumulative, actualStartMs, actualEndMs });
      cumulative += hold;
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
    const finalPath = resolve(dir, "hook-segment.webm");
    renameSync(rawPath, finalPath);
    // The page that was filmed goes next to the video so a later take can be
    // compared against what this one actually rendered.
    copyFileSync(pagePath, resolve(dir, "hook-page.html"));

    writeFileSync(
      resolve(dir, "timeline-hook.json"),
      JSON.stringify(
        {
          video: "hook-segment.webm",
          probe,
          nominalDurationMs: cumulative,
          facts: {
            csvRows: csv.totalRows,
            sheetPrimers: sheet.totalRows,
            fastqFiles: run.fastqFiles,
            barcodeFolders: run.barcodes,
          },
          cuts: entries,
        },
        null,
        2,
      ) + "\n",
      "utf8",
    );
    console.log(`\n[hook] ${entries.length} cuts, ${cumulative}ms nominal -> ${finalPath}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error("[hook] failed:", err);
  process.exit(1);
});
