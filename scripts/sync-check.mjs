#!/usr/bin/env node
// sync-check.mjs — Phase 1 cross-layer consistency checks.
// Reports mismatches only; does not auto-fix. Exit 1 on any failure.
//
// Checks:
//   V) 3-way version sync (package.json / tauri.conf.json / Cargo.toml)
//   R) tauri.conf.json bundle.resources -> files exist on disk
//   K) kuro dispatcher _METHODS  <-> src/types/models.ts RpcMethodMap
//   M) mame dispatcher _METHODS  registered (smoke: presence only)
//
// Add new checks by appending to `checks` array.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];
const passes = [];

function fail(check, msg) {
  failures.push({ check, msg });
}
function pass(check, msg) {
  passes.push({ check, msg });
}

function readJSON(p) {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}
function readText(p) {
  return fs.readFileSync(p, "utf-8");
}

// V) Version 3-way sync ------------------------------------------------------
function checkVersionSync() {
  const pkg = readJSON(path.join(ROOT, "package.json")).version;
  const tauri = readJSON(path.join(ROOT, "src-tauri/tauri.conf.json")).version;
  const cargo = readText(path.join(ROOT, "src-tauri/Cargo.toml"))
    .split("\n")
    .find((l) => /^version\s*=\s*"/.test(l));
  const cargoVer = cargo ? cargo.match(/"([^"]+)"/)?.[1] : null;
  if (pkg === tauri && tauri === cargoVer) {
    pass("V", `versions aligned: ${pkg}`);
  } else {
    fail(
      "V",
      `version drift — package.json=${pkg} tauri.conf.json=${tauri} Cargo.toml=${cargoVer}`,
    );
  }
}

// R) Tauri resources exist ---------------------------------------------------
function checkTauriResources() {
  const conf = readJSON(path.join(ROOT, "src-tauri/tauri.conf.json"));
  const resources = conf?.bundle?.resources;
  if (!resources) {
    pass("R", "no bundle.resources declared");
    return;
  }
  const entries = Array.isArray(resources)
    ? resources.map((src) => ({ src, dest: null }))
    : Object.entries(resources).map(([src, dest]) => ({ src, dest }));
  const tauriDir = path.join(ROOT, "src-tauri");
  let missing = 0;
  for (const { src } of entries) {
    if (src.includes("**") || src.includes("*")) {
      fail("R", `glob pattern not allowed: ${src}`);
      missing++;
      continue;
    }
    const abs = path.resolve(tauriDir, src);
    if (!fs.existsSync(abs)) {
      fail("R", `resource missing on disk: ${src}`);
      missing++;
    }
  }
  if (missing === 0) pass("R", `${entries.length} resources present`);
}

// K) Kuro dispatcher <-> RpcMethodMap ---------------------------------------
const EXCLUDED_METHODS = new Set(["ping", "shutdown", "health_info"]);

function parseDispatcherMethods(filepath) {
  const src = readText(filepath);
  const start = src.indexOf("_METHODS = {");
  if (start === -1) return [];
  const end = src.indexOf("\n}", start);
  const block = src.slice(start, end);
  // top-level keys only: exactly 4-space indent (nested dict keys are deeper)
  return [...block.matchAll(/^ {4}"([a-zA-Z_][\w.]*)"\s*:/gm)].map((m) => m[1]);
}

function parseRpcMethodMap() {
  const src = readText(path.join(ROOT, "src/types/models.ts"));
  const start = src.indexOf("interface RpcMethodMap");
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
  // top-level fields only: exactly 2-space indent inside the interface body
  return [...block.matchAll(/^ {2}([a-zA-Z_][\w]*)\s*:\s*\{/gm)].map((m) => m[1]);
}

function checkKuroMethods() {
  const dispatched = parseDispatcherMethods(
    path.join(ROOT, "python-core/sidecar_kuro/dispatcher.py"),
  ).filter((m) => !EXCLUDED_METHODS.has(m));
  const tsMap = new Set(parseRpcMethodMap());
  const missingInTs = dispatched.filter((m) => !tsMap.has(m));
  const orphanInTs = [...tsMap].filter(
    (m) => !dispatched.includes(m) && !EXCLUDED_METHODS.has(m),
  );
  if (missingInTs.length === 0 && orphanInTs.length === 0) {
    pass("K", `${dispatched.length} kuro methods aligned with RpcMethodMap`);
    return;
  }
  for (const m of missingInTs) fail("K", `kuro dispatcher method "${m}" missing in RpcMethodMap`);
  for (const m of orphanInTs) fail("K", `RpcMethodMap entry "${m}" has no kuro dispatcher handler`);
}

// M) Mame dispatcher presence (smoke) ---------------------------------------
function checkMameMethods() {
  const methods = parseDispatcherMethods(
    path.join(ROOT, "python-core/sidecar_mame/dispatcher.py"),
  );
  if (methods.length === 0) {
    fail("M", "mame dispatcher _METHODS parse returned 0 entries");
  } else {
    pass("M", `${methods.length} mame methods registered`);
  }
}

// ---------------------------------------------------------------------------
const checks = [
  ["V", checkVersionSync],
  ["R", checkTauriResources],
  ["K", checkKuroMethods],
  ["M", checkMameMethods],
];

for (const [name, fn] of checks) {
  try {
    fn();
  } catch (e) {
    fail(name, `check threw: ${e.message}`);
  }
}

const RESET = "\x1b[0m";
const RED = "\x1b[31m";
const GREEN = "\x1b[32m";
const DIM = "\x1b[2m";

for (const { check, msg } of passes) {
  console.log(`${GREEN}PASS${RESET} [${check}] ${DIM}${msg}${RESET}`);
}
for (const { check, msg } of failures) {
  console.log(`${RED}FAIL${RESET} [${check}] ${msg}`);
}

console.log(
  `\n${failures.length === 0 ? GREEN : RED}${passes.length} passed, ${failures.length} failed${RESET}`,
);

process.exit(failures.length === 0 ? 0 : 1);
