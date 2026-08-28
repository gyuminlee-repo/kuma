#!/usr/bin/env node
// Pull one mid-beat frame per section of the finished video for visual review.
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const WORKSPACE = process.env.WORKSPACE_ROOT || path.join(process.env.HOME, '_workspace');
const OUT = process.env.KUMA_INTRO_OUT || path.join(WORKSPACE, 'kuma_intro_video');
const DEST = process.env.FRAME_DIR || '/tmp/finalframes';
const a = JSON.parse(readFileSync(path.join(OUT, 'assembly.json'), 'utf8'));
mkdirSync(DEST, { recursive: true });

const shots = [];
const mid = (s, e) => Math.round(((s + e) / 2) * 100) / 100;
// Section boundaries come from assembly.json rather than being written out here,
// so a hold change in the recorders moves these shots with it instead of
// silently sampling the wrong section.
const section = (name) => {
  const s = a.sections.find((x) => x.name === name);
  if (!s) throw new Error(`assembly.json has no "${name}" section`);
  return s;
};
// hook: one frame per cut. Cut lengths are read from the hook timeline when it
// is beside the video, and otherwise the section is split into equal thirds.
const hook = section('hook');
const hookTl = path.join(process.env.KUMA_INTRO_IN || path.join(REPO, 'docs/.intro-video'), 'timeline-hook.json');
let hookBounds;
if (existsSync(hookTl)) {
  const cuts = JSON.parse(readFileSync(hookTl, 'utf8')).cuts;
  hookBounds = cuts.map((c) => [hook.start + c.startMs / 1000,
    Math.min(hook.end, hook.start + (c.startMs + (c.actualEndMs - c.actualStartMs)) / 1000)]);
} else {
  const step = hook.duration / 3;
  hookBounds = [0, 1, 2].map((i) => [hook.start + i * step, hook.start + (i + 1) * step]);
}
hookBounds.forEach(([s, e], i) => shots.push([`hook-cut${i + 1}`, mid(s, e)]));
// Cut 1 runs long enough that its start and end are separate observations.
const [c1s, c1e] = hookBounds[0];
shots.push(['hook-cut1-early', Math.round((c1s + 1.5) * 100) / 100],
  ['hook-cut1-late', Math.round((c1e - 1.0) * 100) / 100]);
const trans = section('transition');
shots.push(['transition', mid(trans.start, trans.end)]);
for (const [seg, beats] of Object.entries(a.beats)) {
  for (const b of beats) shots.push([`${seg}-${b.screen}`, mid(b.finalIn, b.finalOut)]);
}
const closing = section('closing');
shots.push(['closing', mid(closing.start, closing.end)]);

for (const [name, t] of shots) {
  const f = path.join(DEST, `${String(t).padStart(6, '0')}s_${name}.png`);
  execFileSync('ffmpeg', ['-y', '-ss', String(t), '-i', path.join(OUT, 'intro-cut.mp4'),
    '-frames:v', '1', '-q:v', '2', f], { stdio: ['ignore', 'ignore', 'ignore'] });
  console.log(`${t}s  ${name}`);
}
console.log(`${shots.length} frames -> ${DEST}`);
