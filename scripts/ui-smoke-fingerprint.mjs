#!/usr/bin/env node
/**
 * ui-smoke-fingerprint.mjs
 *
 * Computes a single hash over every frontend source file that can change what
 * `ui-smoke.mjs` verifies (title, root render, KURO/MAME tab render, no
 * pageerror). A hook compares this value against the fingerprint recorded in
 * `.ui-smoke-passed` to decide whether the smoke gate is still valid for the
 * current working tree, or whether it needs to be re-run.
 *
 * Single source of truth: `ui-smoke.mjs` imports `computeFingerprint` from
 * this module rather than reimplementing the hash, so the value written into
 * the marker is always the same one a hook recomputes independently.
 *
 * Scope:
 *   - included: src/** (all files), index.html, vite.config.*, package.json,
 *     tsconfig*.json, tailwind.config.*, postcss.config.*
 *   - excluded: *.test.ts, *.test.tsx, src/test-setup.ts, src/test-utils/**
 *     (test-only edits must not force a UI re-check; requiring one for every
 *     test file touch would make the gate a standing, ignorable warning)
 *   - untracked files that are gitignored are excluded via `--exclude-standard`
 *     (applies only to the untracked half of `git ls-files`; a file that is
 *     both tracked and gitignored would still appear here, but this repo has
 *     none in the included scope)
 *   - hashed from the actual working tree bytes, not HEAD, so uncommitted
 *     edits are covered
 *
 * Algorithm: sort the included paths, concatenate
 * `<repo-relative path>\0<sha256 of file bytes as lowercase hex>\n` for each,
 * and sha256 the resulting string. Output is the final digest as lowercase
 * hex, nothing else, so the hook can consume stdout directly.
 */

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);

function repoRoot() {
  return execFileSync("git", ["rev-parse", "--show-toplevel"], {
    encoding: "utf8",
  }).trim();
}

/**
 * `git ls-files --cached --others --exclude-standard` lists every path that
 * exists in the working tree and is not gitignored, tracked or not. That is
 * exactly "gitignored files are excluded regardless of tracked/untracked
 * state" without a second exclude-standard pass for the untracked half.
 */
function listCandidatePaths(root) {
  const out = execFileSync(
    "git",
    ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    { cwd: root, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
  );
  return out.split("\0").filter(Boolean);
}

const CONFIG_FILE_PATTERNS = [
  /^index\.html$/,
  /^vite\.config\.[cm]?[jt]s$/,
  /^package\.json$/,
  /^tsconfig(\..+)?\.json$/,
  /^tailwind\.config\.[cm]?[jt]s$/,
  /^postcss\.config\.[cm]?[jt]s$/,
];

function isIncluded(relPath) {
  // Normalize to forward slashes: git ls-files already emits '/', but stay
  // defensive on platforms where sep differs.
  const p = relPath.split(sep).join("/");

  if (p.startsWith("src/")) {
    if (p.endsWith(".test.ts") || p.endsWith(".test.tsx")) return false;
    if (p === "src/test-setup.ts") return false;
    if (p.startsWith("src/test-utils/")) return false;
    return true;
  }

  return CONFIG_FILE_PATTERNS.some((re) => re.test(p));
}

/**
 * Returns the file's sha256, or null when the path no longer exists in the
 * working tree. `git ls-files --cached` still lists a tracked file that has
 * been deleted on disk, so reading it unguarded throws ENOENT and takes the
 * whole fingerprint down. A hook that treats a crash as "nothing to say" would
 * then fall silent on exactly the change that deletes a screen, so a missing
 * file must drop out of the list instead: the path itself is hashed, so its
 * absence already moves the fingerprint.
 */
function hashFile(absPath) {
  let bytes;
  try {
    bytes = readFileSync(absPath);
  } catch (error) {
    if (error.code === "ENOENT" || error.code === "EISDIR") return null;
    throw error;
  }
  return createHash("sha256").update(bytes).digest("hex");
}

/**
 * Computes the fingerprint for `root` (defaults to the current repo's
 * toplevel). Returns lowercase hex sha256.
 */
export function computeFingerprint(root = repoRoot()) {
  const candidates = listCandidatePaths(root);
  const included = candidates.filter(isIncluded).sort();

  const digest = createHash("sha256");
  for (const relPath of included) {
    const absPath = resolve(root, relPath);
    const fileHash = hashFile(absPath);
    // Deleted on disk: drop it. The path is part of the hash input, so losing
    // the entry is itself the change the gate needs to notice.
    if (fileHash === null) continue;
    digest.update(relPath, "utf8");
    digest.update("\0");
    digest.update(fileHash, "utf8");
    digest.update("\n");
  }
  return digest.digest("hex");
}

// Run standalone: print the fingerprint and exit 0.
if (process.argv[1] === __filename) {
  console.log(computeFingerprint());
}
