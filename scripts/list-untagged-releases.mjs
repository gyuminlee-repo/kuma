#!/usr/bin/env node
/**
 * list-untagged-releases.mjs
 *
 * Lists the releases this repository announced but never cut a tag for.
 *
 * .github/workflows/build.yml runs on `push: tags: ["v*"]` and on nothing
 * else, so a version reaches users only when someone pushes the tag. Landing a
 * three-component label on main and writing the CHANGELOG section are what
 * announce a release; neither of them builds anything. On 2026-09-14 the
 * newest version tag was v0.16.54 while main had announced v0.16.55, .56, .57
 * and .58, each with its CHANGELOG section. Four announced releases, no
 * artifacts.
 *
 * Deliberately NOT a CI gate. A tag is cut after the merge, so at merge time
 * its absence is the normal state, and a check that fires on the normal state
 * is noise that trains the reader to skip the whole category. This is run when
 * someone is about to cut a release, and it is what RELEASE_CHECKLIST.md
 * points at.
 *
 * The CHANGELOG is the source of announcements rather than the git log,
 * because a section is the deliberate act: a label can land through a squash
 * subject nobody chose.
 *
 * Usage:
 *   node scripts/list-untagged-releases.mjs          # remote tags, needs network
 *   node scripts/list-untagged-releases.mjs --local  # local tags only
 */
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TAG = "[untagged-releases]";
const LOCAL = process.argv.includes("--local");

function git(args) {
  const r = spawnSync("git", args, { cwd: ROOT, encoding: "utf-8" });
  return r.status === 0 ? r.stdout : null;
}

function announced() {
  const text = readFileSync(resolve(ROOT, "CHANGELOG.md"), "utf-8");
  const out = [];
  for (const line of text.split("\n")) {
    const m = /^## v(\d+\.\d+\.\d+)(?:[\s(]|$)/.exec(line);
    if (m) out.push(m[1]);
  }
  return out;
}

function tagged() {
  const raw = LOCAL
    ? git(["tag", "--list", "v*"])
    : git(["ls-remote", "--tags", "origin", "v*"]);
  if (raw === null) {
    throw new Error(
      LOCAL
        ? "`git tag` failed here"
        : "`git ls-remote --tags origin` failed; pass --local to use local tags instead",
    );
  }
  const set = new Set();
  for (const line of raw.split("\n")) {
    const m = /refs\/tags\/v(\d+\.\d+\.\d+)(?:\.\d+)?(?:\^\{\})?$|^v(\d+\.\d+\.\d+)(?:\.\d+)?$/.exec(line.trim());
    if (m) set.add(m[1] ?? m[2]);
  }
  return set;
}

function main() {
  const versions = announced();
  const have = tagged();
  const missing = versions.filter((v) => !have.has(v));

  console.log(`${TAG} source: CHANGELOG.md "## vX.Y.Z" headings vs ${LOCAL ? "local" : "origin"} tags`);
  console.log(`${TAG} ${versions.length} announced release(s), ${have.size} tagged`);

  if (missing.length === 0) {
    console.log(`${TAG} OK: every announced release has a tag`);
  } else {
    console.log(`${TAG} ${missing.length} announced release(s) never built, newest first:`);
    for (const v of missing) console.log(`  v${v}`);
    console.log(`${TAG} To build one, on main at the commit that release describes:`);
    console.log(`  git tag v${missing[0]} && git push origin v${missing[0]}`);
    console.log(`${TAG} Pushing a tag runs .github/workflows/build.yml and publishes artifacts, so this is a human decision, not something CI should do.`);
  }

  console.log(`${TAG} checks: whether each CHANGELOG-announced three-component version has a matching tag.`);
  console.log(`${TAG} does not check: whether a tag points at the right commit; whether the GitHub release for a tag has assets; four-component vA.BB.CC.DD labels, which are not releases; and releases announced only by a commit subject with no CHANGELOG section.`);
  return 0;
}

try {
  process.exit(main());
} catch (err) {
  console.error(`${TAG} FAILED: ${err.message}`);
  process.exit(1);
}
