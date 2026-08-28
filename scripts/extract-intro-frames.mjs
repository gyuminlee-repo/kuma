#!/usr/bin/env node
// Pull one mid-beat frame per section of the finished video for visual review.
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const WORKSPACE = process.env.WORKSPACE_ROOT || path.join(process.env.HOME, '_workspace');
const OUT = process.env.KUMA_INTRO_OUT || path.join(WORKSPACE, 'kuma_intro_video');
const DEST = process.env.FRAME_DIR || '/tmp/finalframes';
const a = JSON.parse(readFileSync(path.join(OUT, 'assembly.json'), 'utf8'));
mkdirSync(DEST, { recursive: true });

const shots = [];
const mid = (s, e) => Math.round(((s + e) / 2) * 100) / 100;
// hook: one frame per 10 s cut, plus a subtitle-bearing frame
shots.push(['hook-cut1', mid(0, 10)], ['hook-cut2', mid(10, 20)], ['hook-cut3', mid(20, 30)]);
shots.push(['transition', mid(30, 45)]);
for (const [seg, beats] of Object.entries(a.beats)) {
  for (const b of beats) shots.push([`${seg}-${b.screen}`, mid(b.finalIn, b.finalOut)]);
}
shots.push(['closing', mid(96.8, 121.8)]);

for (const [name, t] of shots) {
  const f = path.join(DEST, `${String(t).padStart(6, '0')}s_${name}.png`);
  execFileSync('ffmpeg', ['-y', '-ss', String(t), '-i', path.join(OUT, 'intro-cut.mp4'),
    '-frames:v', '1', '-q:v', '2', f], { stdio: ['ignore', 'ignore', 'ignore'] });
  console.log(`${t}s  ${name}`);
}
console.log(`${shots.length} frames -> ${DEST}`);
