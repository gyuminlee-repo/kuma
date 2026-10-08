#!/usr/bin/env node
// rename-bundle-to-tag.mjs
//
// Rename Tauri bundle artifacts so the file name version matches the
// project's 4-part GitHub tag (e.g. v0.9.7.1) instead of Tauri's 3-part
// semver (0.9.7). Runs in CI after `tauri build` on tag pushes only.
//
// Tauri/Cargo enforce SemVer 2.0 MAJOR.MINOR.PATCH, so the in-binary
// version stays 3-part. The 4-part suffix is appended to file names
// only. Tag format: v<A>.<B>.<C>.<D> (CLAUDE.md "Git Convention").
//
// Usage: node scripts/rename-bundle-to-tag.mjs <github-ref-name>
//   e.g. node scripts/rename-bundle-to-tag.mjs v0.9.7.1

import { readdirSync, renameSync, statSync } from "node:fs";
import { join, dirname } from "node:path";

const BUNDLE_ROOT = "src-tauri/target/release/bundle";

function fail(msg) {
  console.error(`[rename-bundle-to-tag] ${msg}`);
  process.exit(1);
}

const tagArg = process.argv[2];
if (!tagArg) fail("missing tag argument (GITHUB_REF_NAME)");

const tagMatch = tagArg.match(/^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$/);
if (!tagMatch) fail(`tag '${tagArg}' is not v<A>.<B>.<C>[.<D>]`);
const [, a, b, c, d] = tagMatch;
const threePart = `${a}.${b}.${c}`;
const fourPart = d !== undefined ? `${threePart}.${d}` : threePart;

if (threePart === fourPart) {
  console.log(`[rename-bundle-to-tag] tag has no 4th component, skip`);
  process.exit(0);
}

function walk(dir, acc = []) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    if (err.code === "ENOENT") return acc;
    throw err;
  }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.isFile()) acc.push(p);
  }
  return acc;
}

const files = walk(BUNDLE_ROOT);
if (files.length === 0) fail(`no files under ${BUNDLE_ROOT}`);

const tokenLiteral = threePart.replace(/\./g, "\\.");
const tokenRegex = new RegExp(`(?<![\\d.])${tokenLiteral}(?![\\d.])`);

let renamed = 0;
for (const src of files) {
  const dir = dirname(src);
  const base = src.slice(dir.length + 1);
  if (!tokenRegex.test(base)) continue;
  const next = base.replace(tokenRegex, fourPart);
  if (next === base) continue;
  const dst = join(dir, next);
  renameSync(src, dst);
  console.log(`[rename-bundle-to-tag] ${base} -> ${next}`);
  renamed += 1;
}

console.log(`[rename-bundle-to-tag] renamed ${renamed} file(s) ` +
  `from ${threePart} -> ${fourPart}`);
