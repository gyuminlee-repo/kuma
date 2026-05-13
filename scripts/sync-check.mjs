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

function autoDetectConfig() {
  // Heuristic fallback when no .cross-layer-sync.json is present: emit a
  // minimal set of checks based on which project markers exist on disk.
  // Used by the global PostToolUse hook so every project gets baseline
  // cross-layer coverage without manual init.
  const checks = [];
  const has = (p) => fs.existsSync(path.join(ROOT, p));
  if (has("package.json") && has("src-tauri/tauri.conf.json") && has("src-tauri/Cargo.toml")) {
    checks.push({
      id: "version-sync",
      type: "version_sync",
      files: [
        { path: "package.json", extract: "json:version" },
        { path: "src-tauri/tauri.conf.json", extract: "json:version" },
        { path: "src-tauri/Cargo.toml", extract: 'regex:^version\\s*=\\s*"([^"]+)"' },
      ],
    });
    checks.push({
      id: "tauri-resources",
      type: "files_exist",
      manifest: "src-tauri/tauri.conf.json",
      extract: "json:bundle.resources",
      base: "src-tauri",
    });
  }
  return { checks };
}

const config = fs.existsSync(configPath)
  ? JSON.parse(fs.readFileSync(configPath, "utf-8"))
  : autoDetectConfig();
if ((config.checks || []).length === 0 && (config.groups || []).length === 0) {
  // Nothing to do; not an error condition for the hook path.
  console.log(`[cross-layer-sync] no checks declared and no auto-detected pattern matched`);
  process.exit(0);
}
const failures = [];
const passes = [];
const warnings = [];

const recordFail = (id, msg) => failures.push({ id, msg });
const recordPass = (id, msg) => passes.push({ id, msg });
const recordWarn = (id, msg) => warnings.push({ id, msg });

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
    recordFail(check.id, `version drift: ${detail}`);
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

// ---- groups[] validity ----------------------------------------------------
// Cross-layer dependency awareness. Each group declares files that must
// co-evolve (CSV columns ↔ Pydantic ↔ TS, etc.). The runner validates that
// files/globs/symbols still resolve; the PostToolUse notify.mjs path emits
// reminders when one of these files is edited.

function globToRegExp(pattern) {
  let re = "";
  let i = 0;
  while (i < pattern.length) {
    const c = pattern[i];
    if (c === "*") {
      if (pattern[i + 1] === "*") { re += ".*"; i += 2; if (pattern[i] === "/") i++; }
      else { re += "[^/]*"; i++; }
    } else if (c === "?") { re += "[^/]"; i++; }
    else if (c === "[") {
      const end = pattern.indexOf("]", i + 1);
      if (end === -1) { re += "\\["; i++; }
      else { re += pattern.slice(i, end + 1); i = end + 1; }
    } else if ("/.+^$()|{}\\".includes(c)) { re += "\\" + c; i++; }
    else { re += c; i++; }
  }
  return new RegExp("^" + re + "$");
}

function isGlob(p) { return /[*?[]/.test(p); }

const IGNORE_DIRS = [/(^|\/)node_modules(\/|$)/, /(^|\/)\.git(\/|$)/, /(^|\/)dist(\/|$)/, /(^|\/)target(\/|$)/, /(^|\/)\.venv(\/|$)/, /(^|\/)\.next(\/|$)/, /(^|\/)__pycache__(\/|$)/, /(^|\/)\.cache(\/|$)/, /(^|\/)build(\/|$)/];

let _allFilesCache = null;
function listAllFiles() {
  if (_allFilesCache) return _allFilesCache;
  const out = [];
  function walk(dir) {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      const rel = path.relative(ROOT, full).split(/[\\/]/).join("/");
      if (IGNORE_DIRS.some((re) => re.test(rel))) continue;
      if (e.isDirectory()) walk(full);
      else if (e.isFile()) out.push(rel);
    }
  }
  walk(ROOT);
  _allFilesCache = out;
  return out;
}

const groups = Array.isArray(config.groups) ? config.groups : [];
const seenIds = new Set();
for (const g of groups) {
  const id = g?.id;
  const sev = g?.severity ?? "blocking";
  const record = (msg) => sev === "warning"
    ? recordWarn("groups-validity", msg)
    : recordFail("groups-validity", msg);
  if (!id) { record("group missing id"); continue; }
  if (seenIds.has(id)) { record(`duplicate id: ${id}`); continue; }
  seenIds.add(id);

  const fileList = (g.files ?? []).filter((f) => typeof f === "string" && f.length > 0);
  let ok = true;
  let allFiles = null;
  for (const pat of fileList) {
    if (isGlob(pat)) {
      const re = globToRegExp(pat);
      allFiles ??= listAllFiles();
      if (!allFiles.some((f) => re.test(f))) {
        record(`glob has no match: ${pat} (group ${id})`);
        ok = false;
      }
    } else if (!fs.existsSync(path.join(ROOT, pat))) {
      record(`file missing: ${pat} (group ${id})`);
      ok = false;
    }
  }

  if (g.symbols?.length && sev === "blocking") {
    const concat = fileList
      .filter((p) => !isGlob(p))
      .map((p) => path.join(ROOT, p))
      .filter((full) => { try { return fs.statSync(full).isFile(); } catch { return false; } })
      .map((full) => { try { return fs.readFileSync(full, "utf-8"); } catch { return ""; } })
      .join("\n");
    for (const sym of g.symbols) {
      const esc = sym.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (!new RegExp(`\\b${esc}\\b`).test(concat)) {
        record(`symbol "${sym}" missing across all files in group ${id}`);
        ok = false;
      }
    }
  }

  if (ok) recordPass("groups-validity", `${id} OK`);
}

// Only emit ANSI when attached to a TTY so hook/CI logs stay clean.
const useColor = process.stdout.isTTY && !process.env.NO_COLOR;
const RESET = useColor ? "\x1b[0m" : "";
const RED = useColor ? "\x1b[31m" : "";
const GREEN = useColor ? "\x1b[32m" : "";
const YELLOW = useColor ? "\x1b[33m" : "";
const DIM = useColor ? "\x1b[2m" : "";

for (const { id, msg } of passes) console.log(`${GREEN}PASS${RESET} [${id}] ${DIM}${msg}${RESET}`);
for (const { id, msg } of warnings) console.log(`${YELLOW}WARN${RESET} [${id}] ${msg}`);
for (const { id, msg } of failures) console.log(`${RED}FAIL${RESET} [${id}] ${msg}`);

const summary = `${passes.length} passed, ${warnings.length} warned, ${failures.length} failed`;
console.log(`\n${failures.length === 0 ? GREEN : RED}${summary}${RESET}`);
process.exit(failures.length === 0 ? 0 : 1);
