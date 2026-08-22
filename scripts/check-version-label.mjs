#!/usr/bin/env node
/**
 * check-version-label.mjs
 *
 * The release manifests must carry the version the commit label claims.
 *
 * `version-sync` in .cross-layer-sync.json compares the five manifests against
 * each other, which catches a partial bump but not a missing one: when every
 * file is still on the previous version they agree perfectly and the check
 * reports "aligned". Nothing compared them against the label on the commit.
 *
 * That gap is reachable, and v0.16.29 reached it. `scripts/sync-version.sh`
 * rewrites the manifests from the HEAD commit subject and runs as a local
 * post-commit hook, so it never runs for a squash merge, which GitHub performs
 * on the server. The result was a commit on main announcing v0.16.29 while
 * KUMA_VERSION still read 0.16.28. That constant is stamped into every
 * .run.json, every hidden __kuma_meta__ sheet and every MAME run report, and
 * src/lib/manifestDiff.ts tells two artifacts apart by it alone, so the two
 * releases would have been indistinguishable in lab provenance.
 *
 * The comparison uses three components. The commit convention is vA.BB.CC.DD
 * while the manifests hold MAJOR.MINOR.PATCH, because Tauri and Cargo enforce
 * SemVer, so the DD suffix belongs to the tag and to bundle names rather than
 * to the files (scripts/sync-version.sh says the same). A DD release therefore
 * agrees with the manifests it does not move.
 *
 * Where the label has to sit: a squash merge writes ONE subject onto main, and
 * GitHub picks it from the pull request title only when the branch holds more
 * than one commit. A single-commit branch is squashed under that commit's own
 * subject, so a labelled pull request title is not enough on its own. v0.16.35
 * and the first attempt at v0.16.35.01 both reached main unlabelled this way,
 * the second one despite a labelled title. Put the label on the commit subject,
 * or pass `gh pr merge --subject` and read back what actually landed.
 *
 * Usage: node scripts/check-version-label.mjs
 */
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LABEL = /^v(\d+\.\d+\.\d+)(?:\.\d+)?:/;

/**
 * How far back to look. The two jobs that run this (frontend-typecheck in
 * ci.yml, quality-gates in build.yml) check out with the same depth, so the
 * window this asks for is the window it gets.
 *
 * Those jobs used to check out at depth 2, on the premise that a squash commit
 * always carries the label and so the label sits at HEAD. That premise is
 * false, and when it fails twice in a row the depth-2 window holds no label at
 * all. The check then reports "skipped" and exits 0, which is how f1ab761a
 * turned a still-broken main green.
 */
const SEARCH_DEPTH = 50;

function git(args) {
  const result = spawnSync("git", args, { cwd: ROOT, encoding: "utf-8" });
  if (result.status !== 0) return null;
  return result.stdout;
}

function manifestVersion() {
  const pkg = JSON.parse(readFileSync(resolve(ROOT, "package.json"), "utf-8"));
  if (typeof pkg.version !== "string" || pkg.version.length === 0) {
    throw new Error("package.json carries no version string");
  }
  return pkg.version;
}

const subjects = git(["log", `-${SEARCH_DEPTH}`, "--format=%s"]);
if (subjects === null) {
  // Not a git checkout, or git is unavailable. A source tarball is a legitimate
  // way to build, and there is no label to check against in one.
  console.log("[version-label] skipped: no git history available here");
  process.exit(0);
}

let labelled = null;
let distance = 0;
for (const subject of subjects.split("\n")) {
  const match = LABEL.exec(subject.trim());
  if (match) {
    labelled = { version: match[1], subject: subject.trim() };
    break;
  }
  distance += 1;
}

if (labelled === null) {
  // A shallow checkout whose few commits happen to be unlabelled, which is the
  // normal shape of a pull request build: GitHub checks out a synthetic merge
  // commit whose subject names two shas. Failing here would flag ordinary
  // branch work, so this reports what it looked at and stops.
  console.log(
    `[version-label] skipped: no vA.BB.CC label in the newest ${SEARCH_DEPTH} ` +
      "commits reachable here (a shallow pull-request checkout looks like this)",
  );
  process.exit(0);
}

const declared = manifestVersion();
if (declared === labelled.version) {
  console.log(`[version-label] OK: manifests and label both say ${declared}`);
  process.exit(0);
}

console.error(
  `[version-label] FAILED: the commit says v${labelled.version} and the ` +
    `manifests say ${declared}.`,
);
console.error(`  commit: ${labelled.subject}`);
if (distance > 0) {
  // HEAD itself carries no label, so the version above was read off an older
  // commit and the manifests are ahead of it rather than behind. That is the
  // shape a squash merge leaves when the pull request title carried no label:
  // GitHub writes the title as the commit subject, and the release commit's
  // own label never reaches main. Telling the reader to run sync-version.sh
  // here would walk the manifests backwards, which is the wrong direction.
  console.error(
    `  HEAD carries no label; the one above is ${distance} commit(s) back, so ` +
      "the manifests are ahead of it rather than behind.",
  );
  console.error(
    "  A squash merge takes its subject from the pull request title. Give the " +
      "title the label the release commit carries, or land a follow-up whose " +
      "subject does, so main states the version its manifests hold.",
  );
  process.exit(1);
}

console.error(
  "  scripts/sync-version.sh rewrites the manifests from the commit subject, " +
    "and it is a local post-commit hook, so it does not run for a squash merge " +
    "performed on the server. Run it on a branch and open a pull request:",
);
console.error("    bash scripts/sync-version.sh");
process.exit(1);
