#!/usr/bin/env node
// scripts/sync-check-groups.mjs
// kuma-deps groups[] validator. Separate from vendored sync-check.mjs to preserve
// upstream refresh path. Reads .cross-layer-sync.json groups[] and reports drift.
//
// Severity:
//   blocking: drift => exit 1 (CI fail)
//   warning : drift => exit 0 with WARN log (CI pass)
//
// Run via `pnpm sync:check` (package.json chains this after sync-check.mjs).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import picomatch from "picomatch";

const ROOT = process.cwd();
const cfgPath = path.join(ROOT, ".cross-layer-sync.json");

if (!fs.existsSync(cfgPath)) {
  console.error("[sync-check-groups] no .cross-layer-sync.json");
  process.exit(0);
}

let cfg;
try {
  cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8"));
} catch (e) {
  console.error(`[sync-check-groups] config parse error: ${e.message}`);
  process.exit(1);
}

const groups = Array.isArray(cfg.groups) ? cfg.groups : [];

const failures = [];
const warnings = [];
const passes = [];

function recordFail(id, msg) { failures.push({ id, msg }); }
function recordWarn(id, msg) { warnings.push({ id, msg }); }
function recordPass(id, msg) { passes.push({ id, msg }); }

const IGNORE_DIRS = [/node_modules/, /\.git/, /dist/, /target/, /\.venv/, /\.next/, /__pycache__/, /\.cache/];

function listAllFiles(root) {
  const out = [];
  function walk(dir) {
    let entries;
    try { entries = fs.readdirSync(dir); } catch { return; }
    for (const e of entries) {
      const full = path.join(dir, e);
      const rel = path.relative(root, full).split(/[\\/]/).join("/");
      if (IGNORE_DIRS.some((re) => re.test(rel))) continue;
      let st;
      try { st = fs.statSync(full); } catch { continue; }
      if (st.isDirectory()) walk(full);
      else out.push(rel);
    }
  }
  walk(root);
  return out;
}

function isGlob(pat) {
  return pat.includes("*") || pat.includes("?") || pat.includes("[");
}

const allFiles = listAllFiles(ROOT);
const ids = new Set();

for (const g of groups) {
  const sev = g.severity ?? "blocking";
  const record = (id, msg) => sev === "warning" ? recordWarn(id, msg) : recordFail(id, msg);

  if (!g.id) {
    recordFail("groups-validity", "group missing id");
    continue;
  }
  if (ids.has(g.id)) {
    record("groups-validity", `duplicate id: ${g.id}`);
    continue;
  }
  ids.add(g.id);

  let groupOk = true;
  const fileList = (g.files ?? []).filter((f) => typeof f === "string" && f.length > 0);
  for (const pat of fileList) {
    if (isGlob(pat)) {
      const matcher = picomatch(pat, { dot: true });
      if (!allFiles.some((f) => matcher(f))) {
        record("groups-validity", `glob has no match: ${pat} (group ${g.id})`);
        groupOk = false;
      }
    } else if (!fs.existsSync(path.join(ROOT, pat))) {
      record("groups-validity", `file missing: ${pat} (group ${g.id})`);
      groupOk = false;
    }
  }

  if (g.symbols?.length && sev === "blocking") {
    const sourcesConcat = (g.files ?? [])
      .filter((pat) => typeof pat === "string" && !isGlob(pat))
      .map((pat) => path.join(ROOT, pat))
      .filter((full) => fs.existsSync(full))
      .filter((full) => {
        try { return fs.statSync(full).isFile(); } catch { return false; }
      })
      .map((full) => {
        try { return fs.readFileSync(full, "utf-8"); } catch { return ""; }
      })
      .join("\n");
    for (const sym of g.symbols) {
      const escaped = sym.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(`\\b${escaped}\\b`);
      if (!re.test(sourcesConcat)) {
        record("groups-validity", `symbol "${sym}" missing across all files in group ${g.id}`);
        groupOk = false;
      }
    }
  }

  if (groupOk) recordPass("groups-validity", `${g.id} OK`);
}

const RESET = "\x1b[0m";
const RED = "\x1b[31m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const DIM = "\x1b[2m";

for (const { id, msg } of passes) console.log(`${GREEN}PASS${RESET} [${id}] ${DIM}${msg}${RESET}`);
for (const { id, msg } of warnings) console.log(`${YELLOW}WARN${RESET} [${id}] ${msg}`);
for (const { id, msg } of failures) console.log(`${RED}FAIL${RESET} [${id}] ${msg}`);

console.log(
  `\n${failures.length === 0 ? GREEN : RED}groups: ${passes.length} passed, ${warnings.length} warned, ${failures.length} failed${RESET}`
);
process.exit(failures.length === 0 ? 0 : 1);
