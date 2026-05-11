#!/usr/bin/env node
// VENDORED from cross-layer-sync skill - DO NOT EDIT.
// Refresh: <dotfiles>/skills/cross-layer-sync/init.mjs --force
// cross-layer-sync/check.mjs — generic config-driven cross-layer consistency runner.
//
// Reads `.cross-layer-sync.json` (or path passed via --config) from the
// project root and executes each check declared therein. Reports drift only;
// does not auto-fix. Exit 1 on any failure.
//
// Supported check types:
//   version_sync   — assert N files extract the same version string.
//   files_exist    — assert paths declared in a manifest exist on disk.
//   registry_match — assert two key sets are equal (with optional excludes).
//   command        — run an arbitrary shell command; non-zero exit = fail.
//
// Extractors (used by version_sync, files_exist):
//   json:<jsonpointer>     — JSON file, dot-path lookup (e.g. json:bundle.resources)
//   regex:<pattern>        — regex with first capture group as result
//   python_dict_keys:<NAME>— top-level keys of a Python `NAME = { ... }` block
//   ts_interface_keys:<NAME>— top-level fields of a TS `interface NAME { ... }` block
//
// See SKILL.md for examples.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const ROOT = process.cwd();

const configIdx = argv.indexOf("--config");
const configPath = configIdx >= 0
  ? path.resolve(ROOT, argv[configIdx + 1])
  : path.join(ROOT, ".cross-layer-sync.json");

if (!fs.existsSync(configPath)) {
  console.error(`[cross-layer-sync] no config at ${path.relative(ROOT, configPath)}`);
  console.error(`Run \`node ${path.relative(ROOT, path.join(HERE, "init.mjs"))}\` to bootstrap.`);
  process.exit(2);
}

const config = JSON.parse(fs.readFileSync(configPath, "utf-8"));
const failures = [];
const passes = [];

const recordFail = (id, msg) => failures.push({ id, msg });
const recordPass = (id, msg) => passes.push({ id, msg });

function readText(p) {
  return fs.readFileSync(path.resolve(ROOT, p), "utf-8");
}

function jsonGet(obj, dotPath) {
  if (!dotPath) return obj;
  return dotPath.split(".").reduce((acc, k) => (acc == null ? acc : acc[k]), obj);
}

function applyExtractor(filePath, extractor) {
  const absPath = path.resolve(ROOT, filePath);
  if (extractor.startsWith("json:")) {
    const pointer = extractor.slice("json:".length);
    return jsonGet(JSON.parse(fs.readFileSync(absPath, "utf-8")), pointer);
  }
  if (extractor.startsWith("regex:")) {
    const pattern = extractor.slice("regex:".length);
    const re = new RegExp(pattern, "m");
    const m = fs.readFileSync(absPath, "utf-8").match(re);
    return m ? m[1] : null;
  }
  if (extractor.startsWith("python_dict_keys:")) {
    const name = extractor.slice("python_dict_keys:".length);
    const src = fs.readFileSync(absPath, "utf-8");
    const start = src.indexOf(`${name} = {`);
    if (start === -1) return [];
    const end = src.indexOf("\n}", start);
    const block = src.slice(start, end);
    // top-level entries only: exactly 4-space indent
    return [...block.matchAll(/^ {4}"([a-zA-Z_][\w.]*)"\s*:/gm)].map((m) => m[1]);
  }
  if (extractor.startsWith("ts_interface_keys:")) {
    const name = extractor.slice("ts_interface_keys:".length);
    const src = fs.readFileSync(absPath, "utf-8");
    const start = src.indexOf(`interface ${name}`);
    if (start === -1) return [];
    const braceOpen = src.indexOf("{", start);
    let depth = 0;
    let end = braceOpen;
    for (let i = braceOpen; i < src.length; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}") {
        depth--;
        if (depth === 0) { end = i; break; }
      }
    }
    const block = src.slice(braceOpen, end);
    return [...block.matchAll(/^ {2}([a-zA-Z_][\w]*)\s*[?:]\s*\{/gm)].map((m) => m[1]);
  }
  throw new Error(`Unknown extractor: ${extractor}`);
}

// ---- check types ----------------------------------------------------------

function runVersionSync(check) {
  const values = check.files.map(({ path: p, extract }) => ({
    path: p,
    value: applyExtractor(p, extract),
  }));
  const distinct = new Set(values.map((v) => v.value));
  if (distinct.size === 1) {
    recordPass(check.id, `aligned: ${[...distinct][0]}`);
  } else {
    const detail = values.map((v) => `${v.path}=${v.value}`).join(" ");
    recordFail(check.id, `version drift — ${detail}`);
  }
}

function runFilesExist(check) {
  const entries = applyExtractor(check.manifest, check.extract);
  const list = Array.isArray(entries)
    ? entries
    : entries && typeof entries === "object"
      ? Object.keys(entries)
      : [];
  const base = path.resolve(ROOT, check.base || ".");
  let missing = 0;
  for (const rel of list) {
    if (typeof rel !== "string") continue;
    if (rel.includes("*")) {
      recordFail(check.id, `glob disallowed: ${rel}`);
      missing++;
      continue;
    }
    if (!fs.existsSync(path.resolve(base, rel))) {
      recordFail(check.id, `missing on disk: ${rel}`);
      missing++;
    }
  }
  if (missing === 0) recordPass(check.id, `${list.length} entries present`);
}

function runRegistryMatch(check) {
  const leftAll = applyExtractor(check.left.path, check.left.extract);
  const rightAll = applyExtractor(check.right.path, check.right.extract);
  const exclude = new Set(check.exclude || []);
  const left = (leftAll || []).filter((k) => !exclude.has(k));
  const right = (rightAll || []).filter((k) => !exclude.has(k));
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  const onlyLeft = left.filter((k) => !rightSet.has(k));
  const onlyRight = right.filter((k) => !leftSet.has(k));
  if (onlyLeft.length === 0 && onlyRight.length === 0) {
    recordPass(check.id, `${left.length} entries aligned`);
    return;
  }
  for (const k of onlyLeft) {
    recordFail(check.id, `"${k}" in ${check.left.path} but not in ${check.right.path}`);
  }
  for (const k of onlyRight) {
    recordFail(check.id, `"${k}" in ${check.right.path} but not in ${check.left.path}`);
  }
}

function runCommand(check) {
  const res = spawnSync(check.run, { shell: true, encoding: "utf-8", cwd: ROOT });
  if (res.status === 0) {
    recordPass(check.id, check.label || check.run);
  } else {
    const msg = (res.stderr || res.stdout || "").trim().split("\n").pop();
    recordFail(check.id, msg || `command failed: ${check.run}`);
  }
}

const RUNNERS = {
  version_sync: runVersionSync,
  files_exist: runFilesExist,
  registry_match: runRegistryMatch,
  command: runCommand,
};

for (const check of config.checks || []) {
  const runner = RUNNERS[check.type];
  if (!runner) {
    recordFail(check.id || check.type, `unknown check type: ${check.type}`);
    continue;
  }
  try {
    runner(check);
  } catch (e) {
    recordFail(check.id || check.type, `threw: ${e.message}`);
  }
}

const RESET = "\x1b[0m";
const RED = "\x1b[31m";
const GREEN = "\x1b[32m";
const DIM = "\x1b[2m";

for (const { id, msg } of passes) console.log(`${GREEN}PASS${RESET} [${id}] ${DIM}${msg}${RESET}`);
for (const { id, msg } of failures) console.log(`${RED}FAIL${RESET} [${id}] ${msg}`);

console.log(`\n${failures.length === 0 ? GREEN : RED}${passes.length} passed, ${failures.length} failed${RESET}`);
process.exit(failures.length === 0 ? 0 : 1);
