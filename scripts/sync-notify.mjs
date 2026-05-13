#!/usr/bin/env node
// VENDORED from cross-layer-sync skill - DO NOT EDIT.
// Refresh: <dotfiles>/skills/cross-layer-sync/init.mjs --force
// cross-layer-sync/notify.mjs — PostToolUse cross-layer dependency notifier.
//
// Reads Claude Code PostToolUse JSON from stdin. If the touched file falls
// inside any `groups[]` declared in `.cross-layer-sync.json`, prints a
// systemMessage listing the sibling files that should be reviewed together.
//
// Drift detect only — never auto-edits. No-match is silent (exit 0).
// Originates from kuma's kuma-deps-notify.mjs, generalised for any project.

import { readFileSync, existsSync, realpathSync } from "node:fs";
import { resolve, relative, sep, posix } from "node:path";

const ALLOWED_TOOLS = new Set(["Edit", "Write", "MultiEdit"]);
const TAG = "[cross-layer-sync]";
const OUTPUT_CAP = 10;

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function toPosix(p) { return p.split(sep).join(posix.sep); }

function realpathOr(p) { try { return realpathSync(p); } catch { return p; } }

function normalizeFilePath(input, cwd) {
  if (!input) return null;
  const abs = realpathOr(resolve(cwd, input));
  const root = realpathOr(cwd);
  const rel = relative(root, abs);
  // Files outside the project root are silently ignored.
  if (rel.startsWith("..")) return null;
  return toPosix(rel);
}

function extractFiles(payload) {
  const ti = payload?.tool_input ?? {};
  if (typeof ti.file_path === "string") return [ti.file_path];
  if (Array.isArray(ti.edits)) {
    return ti.edits.map((e) => e?.file_path).filter((f) => typeof f === "string");
  }
  return [];
}

// Minimal picomatch-compatible glob → RegExp. Avoids adding a runtime dep.
// Supports: `*` (any non-/), `**` (any), `?` (single char), char classes [...].
function globToRegExp(pattern) {
  let re = "";
  let i = 0;
  while (i < pattern.length) {
    const c = pattern[i];
    if (c === "*") {
      if (pattern[i + 1] === "*") {
        re += ".*";
        i += 2;
        if (pattern[i] === "/") i++;
      } else {
        re += "[^/]*";
        i++;
      }
    } else if (c === "?") { re += "[^/]"; i++; }
    else if (c === "[") {
      let end = pattern.indexOf("]", i + 1);
      if (end === -1) { re += "\\["; i++; }
      else { re += pattern.slice(i, end + 1); i = end + 1; }
    } else if ("/.+^$()|{}\\".includes(c)) { re += "\\" + c; i++; }
    else { re += c; i++; }
  }
  return new RegExp("^" + re + "$");
}

function matchGroups(file, groups) {
  return groups.filter((g) =>
    (g.files ?? []).some((pat) => globToRegExp(pat).test(file))
  );
}

function formatOutput(file, groups) {
  const shown = groups.slice(0, OUTPUT_CAP);
  const overflow = groups.length - OUTPUT_CAP;
  const lines = [`${TAG} ${file} 변경 감지`, ""];
  for (const g of shown) {
    lines.push(`▼ 그룹: ${g.id} (severity: ${g.severity ?? "blocking"})`);
    lines.push(`  같이 점검:`);
    for (const f of g.files ?? []) {
      const sym = g.symbols?.length ? ` [symbols: ${g.symbols.join(", ")}]` : "";
      lines.push(`   - ${f}${sym}`);
    }
    if (g.note) lines.push(`  주의: ${g.note}`);
    lines.push("");
  }
  if (overflow > 0) lines.push(`(+${overflow} more groups)`);
  return lines.join("\n");
}

async function main() {
  const raw = await readStdin();
  let payload;
  try { payload = JSON.parse(raw); } catch { process.exit(0); }
  const tool = payload?.tool_name;
  if (!ALLOWED_TOOLS.has(tool)) process.exit(0);

  const cwd = process.cwd();
  const cfgPath = resolve(cwd, ".cross-layer-sync.json");
  if (!existsSync(cfgPath)) process.exit(0);

  let cfg;
  try { cfg = JSON.parse(readFileSync(cfgPath, "utf8")); }
  catch (e) {
    process.stderr.write(`${TAG} config parse error: ${e.message}\n`);
    process.exit(0);
  }
  const groups = Array.isArray(cfg.groups) ? cfg.groups : [];
  if (groups.length === 0) process.exit(0);

  const files = extractFiles(payload)
    .map((f) => normalizeFilePath(f, cwd))
    .filter(Boolean);

  const buckets = new Map();
  for (const f of files) {
    const matched = matchGroups(f, groups);
    if (matched.length > 0) buckets.set(f, matched);
  }
  if (buckets.size === 0) process.exit(0);

  for (const [file, gs] of buckets) {
    process.stdout.write(formatOutput(file, gs));
    process.stdout.write("\n");
  }
  process.exit(0);
}

main().catch((e) => {
  process.stderr.write(`${TAG} unexpected error: ${e.message}\n`);
  process.exit(0);
});
