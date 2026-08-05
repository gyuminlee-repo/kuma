#!/usr/bin/env node
/**
 * The sync gate a pre-push hook can actually pass.
 *
 * `pnpm sync:check` is the CI gate and stays strict. Run against a working
 * checkout it fails on one thing no developer can fix by writing code:
 * `src-tauri/resources/NOTICE.md` is listed in `tauri.conf.json` bundle
 * resources, is produced by `scripts/build-notice.mjs` during a release build,
 * and is gitignored (.gitignore). A fresh clone therefore never has it, so the
 * `tauri-resources` check fails on every push until someone runs a full build.
 *
 * A gate that always fails is not a gate. It taught `git push --no-verify` as
 * the normal way to push, which is how the checks that do work here (version
 * sync, the group registry, What's New freshness) stopped being read at all
 * (2026-08-05).
 *
 * So this wrapper downgrades exactly that one missing generated resource to a
 * warning and keeps everything else fatal. It is deliberately narrow: a missing
 * resource that is not the generated NOTICE still fails, and every other check
 * fails as before. CI keeps running `pnpm sync:check`, where the file exists
 * because the workflow builds it.
 */
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** The one failure a checkout cannot avoid: a gitignored build artefact. */
const GENERATED_RESOURCE = /^FAIL \[tauri-resources\].*missing on disk: resources\/NOTICE\.md\s*$/;

const STAGES = [
  { name: "sync-check", cmd: ["node", "scripts/sync-check.mjs"], tolerate: GENERATED_RESOURCE },
  { name: "sync-check-groups", cmd: ["node", "scripts/sync-check-groups.mjs"] },
  { name: "gen-whatsnew", cmd: ["node", "scripts/gen-whatsnew.mjs", "--check"] },
];

const failed = [];
const warned = [];

for (const stage of STAGES) {
  const result = spawnSync(stage.cmd[0], stage.cmd.slice(1), {
    cwd: ROOT,
    encoding: "utf8",
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  process.stdout.write(output);
  if (result.status === 0) continue;

  const failures = output
    .split("\n")
    .filter((line) => line.startsWith("FAIL ["));
  const tolerated =
    stage.tolerate !== undefined &&
    failures.length > 0 &&
    failures.every((line) => stage.tolerate.test(line));

  if (tolerated) {
    warned.push(`${stage.name}: ${failures.length} generated-artefact check(s)`);
  } else {
    failed.push(stage.name);
  }
}

for (const warning of warned) {
  console.warn(
    `[pre-push] warning, ${warning}. Run a release build (or pnpm run build:all) to produce it; CI checks it strictly.`,
  );
}

if (failed.length > 0) {
  console.error(`[pre-push] sync FAILED: ${failed.join(", ")}`);
  process.exit(1);
}

console.log("[pre-push] sync OK");
