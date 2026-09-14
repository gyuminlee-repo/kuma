#!/usr/bin/env node
/**
 * check-landing-label.mjs
 *
 * Checks the version label that a pull request will actually put on main,
 * before the merge rather than after it.
 *
 * scripts/check-version-label.mjs compares the newest label in the history it
 * can see against the manifests. On a pull request the history it sees is the
 * branch, so it reads the branch HEAD's subject. That is not the subject the
 * merge writes. A squash merge writes ONE subject onto main and GitHub picks
 * it by the repository's squash_merge_commit_title setting, which here is
 * COMMIT_OR_PR_TITLE (read from `gh api repos/:owner/:repo` on 2026-09-14):
 * the pull request title when the branch holds more than one commit, the
 * single commit's own subject when it holds exactly one.
 *
 * So the checked subject and the landed subject are two different strings, and
 * pull request 391 is what that costs. Its branch HEAD said v0.16.58.05, which
 * agrees with manifests on 0.16.58, so the gate passed. Its title said
 * v0.16.59 and the branch held three commits, so v0.16.59 is what landed, and
 * main went red on 56805545 against manifests that still read 0.16.58. The
 * docstring of check-version-label.mjs already described this failure mode. It
 * was written down and never turned into a check.
 *
 * Two things are checked here, both against the computed landing subject.
 *
 * A. Label against manifests. The comparison uses three components, as
 *    check-version-label.mjs explains: the commit convention is vA.BB.CC.DD
 *    while package.json holds MAJOR.MINOR.PATCH, because Tauri and Cargo
 *    enforce SemVer. A .DD label therefore agrees with manifests it does not
 *    move.
 *
 * B. Release requirements. A three-component label (vA.BB.CC:, no .DD) is a
 *    claim that this is a release. Then CHANGELOG.md must carry that version's
 *    section. Tag presence is deliberately NOT checked: a tag is cut after the
 *    merge, so its absence at merge time is normal. See
 *    scripts/list-untagged-releases.mjs for that side.
 *
 * Usage:
 *   node scripts/check-landing-label.mjs                 # reads $GITHUB_EVENT_PATH
 *   node scripts/check-landing-label.mjs --event <file>  # reads a payload file
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LABEL = /^v(\d+\.\d+\.\d+)(\.\d+)?:/;
const TAG = "[landing-label]";

function arg(name) {
  const i = process.argv.indexOf(name);
  return i === -1 ? null : process.argv[i + 1];
}

function git(args) {
  const r = spawnSync("git", args, { cwd: ROOT, encoding: "utf-8" });
  return r.status === 0 ? r.stdout.trim() : null;
}

function manifestVersion() {
  const pkg = JSON.parse(readFileSync(resolve(ROOT, "package.json"), "utf-8"));
  if (typeof pkg.version !== "string" || pkg.version.length === 0) {
    throw new Error("package.json carries no version string");
  }
  return pkg.version;
}

function footer() {
  console.log(`${TAG} checks: the subject a squash merge would write onto main, ` +
    "computed from the pull request title, its commit count and, for a " +
    "single-commit branch, that commit's subject; its three-component version " +
    "against package.json; and, when the label claims a release (no .DD), the " +
    "presence of that version's CHANGELOG.md section.");
  console.log(`${TAG} does not check: a landing subject that carries no label ` +
    "at all (reported, not failed); a squash message typed by hand into the " +
    "merge dialog, which overrides the computed title; a merge-commit or " +
    "rebase merge, neither of which this repository uses; whether a release " +
    "tag exists, which is a post-merge act (scripts/list-untagged-releases.mjs " +
    "covers that); and the other four manifests, which version-sync in " +
    ".cross-layer-sync.json ties to package.json.");
}

function main() {
  const eventPath = arg("--event") ?? process.env.GITHUB_EVENT_PATH;
  if (!eventPath || !existsSync(eventPath)) {
    console.log(`${TAG} skipped: no event payload (looked at ${eventPath ?? "$GITHUB_EVENT_PATH, unset"})`);
    return 0;
  }
  const event = JSON.parse(readFileSync(eventPath, "utf-8"));
  const pr = event.pull_request;
  if (!pr) {
    console.log(`${TAG} skipped: the payload carries no pull_request object, so no merge is being proposed`);
    return 0;
  }

  const title = typeof pr.title === "string" ? pr.title.trim() : "";
  const commits = Number(pr.commits);
  if (!Number.isInteger(commits) || commits < 1) {
    console.error(`${TAG} FAILED: the payload has no usable pull_request.commits count (saw ${JSON.stringify(pr.commits)}), so the landing subject cannot be computed`);
    return 1;
  }

  let landing;
  let origin;
  if (commits === 1) {
    const sha = pr.head?.sha;
    const subject = sha ? git(["log", "-1", "--format=%s", sha]) : null;
    if (subject === null) {
      console.error(`${TAG} FAILED: the branch holds one commit, so its own subject is what lands, but ${sha ?? "head.sha"} is not readable in this checkout. Increase fetch-depth or fetch the head sha.`);
      return 1;
    }
    landing = subject;
    origin = `the branch's single commit ${String(sha).slice(0, 8)} (GitHub squashes a one-commit branch under its own subject, so the title is not used)`;
  } else {
    landing = title;
    origin = `the pull request title (the branch holds ${commits} commits, so GitHub squashes under the title)`;
  }

  console.log(`${TAG} landing subject: ${landing}`);
  console.log(`${TAG} taken from ${origin}`);

  const match = LABEL.exec(landing);
  if (match === null) {
    console.log(`${TAG} no vA.BB.CC label on the landing subject, so there is nothing to compare against the manifests here.`);
    console.log(`${TAG} Note that main then states no new version: scripts/check-version-label.mjs will keep reading the previous label.`);
    footer();
    return 0;
  }

  const [, version, dd] = match;
  const declared = manifestVersion();
  const problems = [];

  if (version !== declared) {
    problems.push(
      `the landing subject says v${version} and package.json says ${declared}. ` +
        "After the merge, scripts/check-version-label.mjs on main reads this " +
        "subject and fails. Either retitle so the label's three components " +
        "read " + declared + ", or bump the manifests on this branch with " +
        "`bash scripts/sync-version.sh` and commit them.",
    );
  }

  if (!dd) {
    const changelog = readFileSync(resolve(ROOT, "CHANGELOG.md"), "utf-8");
    const heading = new RegExp(`^## v${version.replace(/\./g, "\\.")}(?=[\\s(]|$)`, "m");
    if (!heading.test(changelog)) {
      problems.push(
        `v${version} is a three-component label, which claims a release, but ` +
          `CHANGELOG.md has no "## v${version}" section. Add the section, or ` +
          "use a four-component vA.BB.CC.DD label, which is not a release claim.",
      );
    }
  }

  if (problems.length > 0) {
    console.error(`${TAG} FAILED: the subject that would land on main does not hold up`);
    for (const p of problems) console.error(`  - ${p}`);
    footer();
    return 1;
  }

  console.log(
    `${TAG} OK: v${version}${dd ?? ""} would land, manifests say ${declared}` +
      (dd ? ", and a .DD label makes no release claim" : `, and CHANGELOG.md carries the v${version} section`),
  );
  footer();
  return 0;
}

try {
  process.exit(main());
} catch (err) {
  console.error(`${TAG} FAILED: ${err.message}`);
  process.exit(1);
}
