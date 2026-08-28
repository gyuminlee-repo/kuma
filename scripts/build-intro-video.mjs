#!/usr/bin/env node
/**
 * build-intro-video.mjs - final assembly of the kuma intro video.
 *
 * Assumptions (stated explicitly, per karpathy-guidelines):
 *  - Recorded segments are 1920x1080 VP8 webm at 25 fps and already exist.
 *  - Beat boundaries come from the timeline JSON files written by the recorder
 *    (actualStartMs / actualEndMs). Boundaries past the real file duration are
 *    clamped to it.
 *  - Order is KURO, MAME, closing card. The video opens on the app itself.
 *  - Waiting/idle footage between beats is discarded with hard cuts.
 *  - Output is silent H.264, 25 fps, CRF 18, 1920x1080.
 *
 * Usage: node scripts/build-intro-video.mjs
 * Override the output directory with KUMA_INTRO_OUT.
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, rmSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const IN = path.join(REPO, 'docs/.intro-video');
const WORKSPACE = process.env.WORKSPACE_ROOT || path.join(process.env.HOME, '_workspace');
const OUT = process.env.KUMA_INTRO_OUT || path.join(WORKSPACE, 'kuma_intro_video');
const WORK = path.join(OUT, 'work');

// kuro-segment.webm + timeline.json live in OUT; the rest live in IN.
const SRC = {
  kuro: path.join(OUT, 'kuro-segment.webm'),
  mame: path.join(IN, 'mame-segment.webm'),
};
const TL = {
  kuro: path.join(OUT, 'timeline.json'),
  mame: path.join(IN, 'timeline-mame.json'),
};

const FPS = 25;
const CRF_INTERMEDIATE = '14';
const CRF_FINAL = '18';
const CLOSING_DURATION = 12.0;
// The closing text is laid over a frozen, darkened frame of the app rather than a
// blank card, so the last thing on screen is still the thing being shown. Taken
// from the middle of the MAME verdict-plate beat.
const CLOSING_BG_SOURCE_S = 114.0;

const sh = (bin, args) => execFileSync(bin, args, { stdio: ['ignore', 'pipe', 'inherit'] }).toString();
const probeDuration = (f) => parseFloat(sh('ffprobe', [
  '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).trim());
const r3 = (n) => Math.round(n * 1000) / 1000;

// ---------------------------------------------------------------- subtitles
// VERBATIM copy. Do not reword: every figure here was measured against the app.
const KURO_SUBS = {
  // Carries what the deleted transition card used to say. This is the first
  // beat of the video, so nothing else states what kuma is.
  '02-file-loaded': ['kuma designs the primers and then reads the sequencing', 'that says what the lab built. One plasmid, 561 residues.'],
  '03-mutations-entered': ['The model ranked 10,528 mutations. 95 of them go to the plate.'],
  '10-designing': ['Primer design for a full plate runs in about two seconds.'],
  '04-design-complete': ['95 of 95 designed.'],
  '11-rescued-rows': ['Three needed the engine to widen its own limits,', 'and it names which three.'],
  '16-design-report': ['Melting temperatures, plate counts,', 'and the rule each primer met.'],
  '05-plate-map': ['The 96-well layout is the order sheet.'],
  '17-mapping-export': ['The export already knows where it goes.', 'The verification side reads this same file.'],
};
const MAME_SUBS = {
  '02-inputs-filled': ['Three weeks later, one sequencing run comes back.', 'Point kuma at the folder as it came off the sequencer, unsorted.'],
  '07-native-barcodes': ['Three barcodes were used.', 'The app finds them rather than asking.'],
  '09-verdict-plate': ['288 wells. 234 pass, 54 fail,', 'and every verdict carries the reads behind it.'],
  '10-replicate-distribution': ['Three plates of the same 96 variants, scored separately.'],
  '08-run-quality': ['Median depth 571 against a 1500 target.', 'The number is shown rather than smoothed.'],
};
const BEAT_SUB_PAD = 0.3; // show 0.3 s after a beat starts, hide 0.3 s before it ends

// ------------------------------------------------------------ still cards
async function renderClosingCard(png, bgPng) {
  const html = path.join(WORK, 'closing.html');
  writeFileSync(html, `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;width:1920px;height:1080px;background:#0f1216;}
  /* The app frame sits behind the text: blurred so it reads as texture rather
     than as a screen the viewer should be parsing, and dimmed by a scrim. The
     scrim is heavier than a nominal 50% because the app is light themed, and
     white text over a 50% dimmed white UI has no contrast left. */
  .bg{position:fixed;inset:0;background:#0f1216 url("file://${bgPng}") center/cover no-repeat;
      filter:blur(9px) brightness(0.42) saturate(0.75);transform:scale(1.04);}
  .scrim{position:fixed;inset:0;background:rgba(15,18,22,0.46);}
  body{position:relative;display:flex;flex-direction:column;justify-content:center;align-items:center;
       font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;color:#f2f4f7;
       -webkit-font-smoothing:antialiased;text-shadow:0 2px 18px rgba(0,0,0,0.75);}
  .wrap{position:relative;display:flex;flex-direction:column;justify-content:center;align-items:center;
        width:100%;height:100%;}
  .a{font-size:62px;font-weight:600;letter-spacing:-0.5px;}
  .u{font-size:52px;font-weight:400;color:#7fc4ff;margin-top:18px;font-family:"SF Mono",Menlo,monospace;}
  .b{font-size:44px;font-weight:400;color:#c3c9d2;margin-top:96px;text-align:center;}
  .c{font-size:38px;font-weight:400;color:#8b929c;margin-top:96px;}
</style>
<div class="bg"></div><div class="scrim"></div>
<div class="wrap">
<div class="a">Download for Windows, macOS and Linux</div>
<div class="u">github.com/gyuminlee-repo/kuma</div>
<div class="b">Help &gt; Load Sample Data runs the whole thing without your own data</div>
<div class="c">Available in 10 languages.&nbsp;&nbsp;GPL v2.</div>
</div>`);
  const { chromium } = await import('playwright');
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto('file://' + html);
  await page.screenshot({ path: png });
  await browser.close();
}

const stillToVideo = (png, seconds, out) => sh('ffmpeg', [
  '-y', '-loop', '1', '-framerate', String(FPS), '-t', String(seconds), '-i', png,
  '-c:v', 'libx264', '-crf', CRF_INTERMEDIATE, '-preset', 'medium',
  '-pix_fmt', 'yuv420p', '-r', String(FPS), '-an', out]);

const cutBeat = (src, start, dur, out) => sh('ffmpeg', [
  '-y', '-accurate_seek', '-ss', String(start), '-i', src, '-t', String(dur),
  '-c:v', 'libx264', '-crf', CRF_INTERMEDIATE, '-preset', 'medium',
  '-pix_fmt', 'yuv420p', '-r', String(FPS), '-fps_mode', 'cfr', '-an', out]);

// -------------------------------------------------------------- subtitles io
const ts = (s) => {
  const ms = Math.round(s * 1000);
  const h = String(Math.floor(ms / 3600000)).padStart(2, '0');
  const m = String(Math.floor(ms / 60000) % 60).padStart(2, '0');
  const sec = String(Math.floor(ms / 1000) % 60).padStart(2, '0');
  return { srt: `${h}:${m}:${sec},${String(ms % 1000).padStart(3, '0')}`,
           ass: `${Number(h)}:${m}:${sec}.${String(Math.round((ms % 1000) / 10)).padStart(2, '0')}` };
};
const writeSrt = (cues, file) => writeFileSync(file, cues.map((c, i) =>
  `${i + 1}\n${ts(c.in).srt} --> ${ts(c.out).srt}\n${c.lines.join('\n')}\n`).join('\n'));

// Written with PlayRes locked to 1920x1080 so FontSize is in real output pixels.
// (An SRT handed straight to libass is laid out in a 384x288 space, where the
// same number would render at roughly a quarter of the intended size.)
const writeAss = (cues, file) => writeFileSync(file, `[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Helvetica Neue,46,&H00FFFFFF,&H000000FF,&H4D000000,&H4D000000,0,0,0,0,100,100,0,0,3,14,0,2,120,120,44,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${cues.map((c) => `Dialogue: 0,${ts(c.in).ass},${ts(c.out).ass},Main,,0,0,0,,${c.lines.join('\\N')}`).join('\n')}
`);

// ------------------------------------------------------------------- main
async function main() {
  rmSync(WORK, { recursive: true, force: true });
  mkdirSync(WORK, { recursive: true });
  for (const [k, f] of Object.entries(SRC)) if (!existsSync(f)) throw new Error(`missing source ${k}: ${f}`);

  const parts = [];   // { file, label, duration }
  const cues = [];    // absolute-time subtitle cues
  let clock = 0;
  const push = (file, label, duration) => { parts.push({ file, label, duration }); clock = r3(clock + duration); };

  // 1 + 2. beat-sliced app segments. Frame 0 of the video is the first frame of
  // the first KURO beat: the app with a plasmid already loaded.
  const beatReport = {};
  for (const [name, subs, idx] of [['kuro', KURO_SUBS, '01'], ['mame', MAME_SUBS, '02']]) {
    const srcDur = probeDuration(SRC[name]);
    const beats = JSON.parse(readFileSync(TL[name], 'utf8')).beats;
    const segStart = clock;
    let offset = 0;
    const files = [];
    beatReport[name] = [];
    beats.forEach((b, i) => {
      const start = b.actualStartMs / 1000;
      // The measured end is an upper bound, not the dwell. Playwright's
      // waitForTimeout can return late when the page stalls the timer, and one
      // KURO take put 49.5 s on a 6.5 s beat that way, all of it the same
      // static export screen. The nominal hold is what the beat was designed
      // for and what the subtitle timing is computed against, so the beat is
      // capped at it. The measured end and the file duration still clamp from
      // above, for a take that ended early or short of the boundary.
      const nominalEnd = b.actualStartMs / 1000 + (b.hold ?? Infinity) / 1000;
      const end = Math.min(nominalEnd, b.actualEndMs / 1000, srcDur);
      const dur = r3(end - start);
      const f = path.join(WORK, `${idx}-${name}-${String(i).padStart(2, '0')}.mp4`);
      cutBeat(SRC[name], start, dur, f);
      files.push(f);
      const lines = subs[b.screen];
      if (!lines) throw new Error(`no subtitle text for beat ${b.screen}`);
      cues.push({
        in: r3(segStart + offset + BEAT_SUB_PAD),
        out: r3(segStart + offset + dur - BEAT_SUB_PAD),
        lines,
      });
      beatReport[name].push({ screen: b.screen, sourceIn: r3(start), sourceOut: r3(end),
        finalIn: r3(segStart + offset), finalOut: r3(segStart + offset + dur), duration: dur });
      offset = r3(offset + dur);
    });
    // concatenate the beats of this segment into one part (hard cuts)
    const listFile = path.join(WORK, `${idx}-${name}.txt`);
    writeFileSync(listFile, files.map((f) => `file '${f}'`).join('\n') + '\n');
    const segFile = path.join(WORK, `${idx}-${name}.mp4`);
    sh('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', listFile, '-c', 'copy', segFile]);
    push(segFile, name, offset);
  }

  // 3. closing card: no subtitles, the card is the text
  const closeBg = path.join(WORK, 'closing-bg.png');
  sh('ffmpeg', ['-y', '-v', 'error', '-accurate_seek', '-ss', String(CLOSING_BG_SOURCE_S),
    '-i', SRC.mame, '-frames:v', '1', closeBg]);
  const closePng = path.join(WORK, 'closing.png');
  const closeFile = path.join(WORK, '03-closing.mp4');
  await renderClosingCard(closePng, closeBg);
  stillToVideo(closePng, CLOSING_DURATION, closeFile);
  push(closeFile, 'closing', CLOSING_DURATION);

  // ------- subtitle files
  const srt = path.join(OUT, 'subtitles.srt');
  const ass = path.join(WORK, 'subtitles.ass');
  writeSrt(cues, srt);
  writeAss(cues, ass);
  const emdash = String.fromCharCode(0x2014);
  for (const c of cues) if (c.lines.join('').includes(emdash)) throw new Error(`em dash in subtitle: ${c.lines}`);

  // ------- concatenate everything
  const listAll = path.join(WORK, 'all.txt');
  writeFileSync(listAll, parts.map((p) => `file '${p.file}'`).join('\n') + '\n');
  const nosub = path.join(OUT, 'intro-cut-nosub.mp4');
  sh('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', listAll,
    '-c:v', 'libx264', '-crf', CRF_FINAL, '-preset', 'slow',
    '-pix_fmt', 'yuv420p', '-r', String(FPS), '-movflags', '+faststart', '-an', nosub]);
  const withsub = path.join(OUT, 'intro-cut.mp4');
  sh('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', listAll,
    '-vf', `subtitles=${ass}`,
    '-c:v', 'libx264', '-crf', CRF_FINAL, '-preset', 'slow',
    '-pix_fmt', 'yuv420p', '-r', String(FPS), '-movflags', '+faststart', '-an', withsub]);

  // ------- assembly record
  let acc = 0;
  const sections = parts.map((p) => { const s = { name: p.label, start: r3(acc), end: r3(acc + p.duration), duration: r3(p.duration) }; acc = r3(acc + p.duration); return s; });
  writeFileSync(path.join(OUT, 'assembly.json'), JSON.stringify({
    generatedAt: new Date().toISOString(),
    order: parts.map((p) => p.label),
    totalDuration: r3(acc),
    fps: FPS, width: 1920, height: 1080, crf: Number(CRF_FINAL),
    sections, beats: beatReport,
    subtitles: cues.map((c) => ({ start: c.in, end: c.out, text: c.lines.join(' ') })),
    outputs: { withSubtitles: withsub, withoutSubtitles: nosub, srt, ass },
  }, null, 2));
  console.log(`done. total ${r3(acc)} s`);
}
main().catch((e) => { console.error(e); process.exit(1); });
