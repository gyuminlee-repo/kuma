#!/usr/bin/env node
/**
 * sync-check-all.mjs
 *
 * Wrapper for the "sync:check" npm script. Previously `sync:check` was a
 * `&&`-chained sequence of three commands:
 *
 *   node scripts/sync-check.mjs && node scripts/sync-check-groups.mjs && node scripts/gen-whatsnew.mjs --check
 *
 * Each stage prints its own summary line. That is misleading when the first
 * two stages pass (sync-check-groups.mjs prints something like
 * "46 passed, 3 warned, 0 failed") and only the third stage (the What's New
 * generator freshness check) fails: the passing summary is what a reader
 * scrolling a CI log sees, and the real failure can be missed. This wrapper
 * runs every stage regardless of earlier failures (so no diagnostic output
 * from a later stage is lost the way `&&` chaining would lose it), then
 * prints one unambiguous final verdict line and sets the overall exit code.
 *
 * Usage: node scripts/sync-check-all.mjs
 */
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const STAGES = [
  { name: "sync-check", cmd: ["node", "scripts/sync-check.mjs"] },
  { name: "sync-check-groups", cmd: ["node", "scripts/sync-check-groups.mjs"] },
  { name: "gen-whatsnew", cmd: ["node", "scripts/gen-whatsnew.mjs", "--check"] },
];

const failedStages = [];

for (const stage of STAGES) {
  const result = spawnSync(stage.cmd[0], stage.cmd.slice(1), {
    cwd: ROOT,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    failedStages.push(stage.name);
  }
}

if (failedStages.length > 0) {
  console.error(`[sync:check] FAILED: ${failedStages.join(", ")}`);
  process.exit(1);
}

console.log("[sync:check] OK");
