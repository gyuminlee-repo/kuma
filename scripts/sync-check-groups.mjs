#!/usr/bin/env node
// sync-check-groups.mjs - co-evolve hygiene for .cross-layer-sync.json groups[].
//
// Assumptions:
//   - Vendored scripts/sync-check.mjs already validates each group's files
//     and symbols exist on disk. This script adds COMMIT-HYGIENE checks that
//     complement (not duplicate) that runner.
//   - Generated-file freshness (e.g. models.generated.ts) is owned by
//     `node scripts/gen-models.mjs --check`. Not re-checked here.
//
// Two checks per blocking group (warning-severity groups are reported as WARN):
//   1) PARTIAL-STAGE: user has staged one file in the group while another
//      group sibling has unstaged modifications. Almost always a mistake.
//      -> FAIL (blocking) / WARN (warning).
//   2) HEAD-PARTIAL: the last commit (HEAD) modified some but not all
//      non-glob files in the group. Heuristic; emitted as WARN regardless
//      of severity to keep CI signal high.
//
// External deps: none (Node fs + child_process only). Exit 1 on any FAIL.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const CONFIG_PATH = path.join(ROOT, ".cross-layer-sync.json");

if (!fs.existsSync(CONFIG_PATH)) {
  console.log("[sync-check-groups] no .cross-layer-sync.json, skip");
  process.exit(0);
}

const config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
const groups = Array.isArray(config.groups) ? config.groups : [];
if (groups.length === 0) {
  console.log("[sync-check-groups] no groups declared, skip");
  process.exit(0);
}

function git(args) {
  const res = spawnSync("git", args, { cwd: ROOT, encoding: "utf-8" });
  if (res.status !== 0) return null;
  return res.stdout;
}

// Confirm we are inside a git repo; if not, nothing to check.
if (git(["rev-parse", "--is-inside-work-tree"]) == null) {
  console.log("[sync-check-groups] not a git work tree, skip");
  process.exit(0);
}

const isGlob = (p) => /[*?[]/.test(p);

const headFiles = new Set(
  (git(["diff", "--name-only", "HEAD~1", "HEAD"]) || "")
    .split("\n").map((s) => s.trim()).filter(Boolean),
);
const stagedFiles = new Set(
  (git(["diff", "--name-only", "--cached"]) || "")
    .split("\n").map((s) => s.trim()).filter(Boolean),
);
const unstagedFiles = new Set(
  (git(["diff", "--name-only"]) || "")
    .split("\n").map((s) => s.trim()).filter(Boolean),
);

const fails = [];
const warns = [];
const passes = [];

for (const g of groups) {
  const id = g?.id ?? "<no-id>";
  const sev = g?.severity ?? "blocking";
  const files = (g.files ?? []).filter((f) => typeof f === "string" && !isGlob(f));
  if (files.length < 2) {
    passes.push(`${id} skipped (single concrete file)`);
    continue;
  }

  // (1) Partial-stage check.
  const stagedInGroup = files.filter((f) => stagedFiles.has(f));
  const unstagedSiblings = files.filter(
    (f) => !stagedFiles.has(f) && unstagedFiles.has(f),
  );
  if (stagedInGroup.length > 0 && unstagedSiblings.length > 0) {
    const msg = `${id} partial-stage: staged=[${stagedInGroup.join(", ")}] but sibling has unstaged edits=[${unstagedSiblings.join(", ")}]`;
    if (sev === "blocking") fails.push(msg);
    else warns.push(msg);
    continue;
  }

  // (2) HEAD-partial check (advisory warning).
  const touched = files.filter((f) => headFiles.has(f));
  if (touched.length > 0 && touched.length < files.length) {
    const untouched = files.filter((f) => !headFiles.has(f));
    warns.push(
      `${id} HEAD touched ${touched.length}/${files.length} (missing: ${untouched.join(", ")})`,
    );
    continue;
  }

  passes.push(`${id} OK`);
}

const useColor = process.stdout.isTTY && !process.env.NO_COLOR;
const RESET = useColor ? "\x1b[0m" : "";
const RED = useColor ? "\x1b[31m" : "";
const GREEN = useColor ? "\x1b[32m" : "";
const YELLOW = useColor ? "\x1b[33m" : "";
const DIM = useColor ? "\x1b[2m" : "";

for (const m of passes) console.log(`${GREEN}PASS${RESET} [groups] ${DIM}${m}${RESET}`);
for (const m of warns) console.log(`${YELLOW}WARN${RESET} [groups] ${m}`);
for (const m of fails) console.log(`${RED}FAIL${RESET} [groups] ${m}`);

console.log(
  `\n${fails.length === 0 ? GREEN : RED}${passes.length} passed, ${warns.length} warned, ${fails.length} failed${RESET}`,
);
process.exit(fails.length === 0 ? 0 : 1);
