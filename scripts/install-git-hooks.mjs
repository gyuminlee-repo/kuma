#!/usr/bin/env node
/**
 * install-git-hooks.mjs
 *
 * Writes the post-commit hook that runs scripts/sync-version.sh (which keeps
 * package.json / src-tauri/tauri.conf.json / src-tauri/Cargo.toml / pyproject.toml
 * / the What's New highlights in src/locales/en.json aligned after a
 * `vX.Y.Z: ...` release commit).
 *
 * .git/hooks is not tracked by git, so a fresh clone has no post-commit hook
 * until this script runs once. It is not a package.json lifecycle script:
 * .npmrc sets ignore-scripts=true for supply-chain hardening, so a "prepare"
 * or "postinstall" entry would never fire. What runs it is
 * scripts/safe-install.mjs (the "setup" package script), which calls this file
 * explicitly once its install attempt has succeeded; it can also be run by
 * hand with `node scripts/install-git-hooks.mjs`.
 *
 * Safe by construction:
 *   - No-op (exit 0, silent) when not inside a git checkout at all (tarball
 *     checkout, some CI caches restore node_modules without .git).
 *   - Works for both a plain clone and a `git worktree` checkout: hooks are
 *     resolved via `git rev-parse --git-path hooks`, which points at the
 *     shared hooks dir in the latter case (worktrees do not get their own
 *     hooks dir), never at a worktree-local path that would silently do
 *     nothing.
 *   - Idempotent: re-running with the same hook content is a no-op, not a
 *     duplicate write.
 *   - Never overwrites a pre-existing post-commit hook whose content differs
 *     from what this script would write; it warns and leaves it alone so a
 *     developer's own hook is never clobbered.
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync, chmodSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const HOOK_CONTENT =
  "#!/usr/bin/env bash\n" +
  "# Auto-sync version from commit message (vX.Y.Z:) to package.json, tauri.conf.json, Cargo.toml\n" +
  'exec "$(git rev-parse --show-toplevel)/scripts/sync-version.sh"\n';

function main() {
  const gitPath = spawnSync("git", ["rev-parse", "--git-path", "hooks"], {
    cwd: ROOT,
    encoding: "utf-8",
  });
  if (gitPath.status !== 0 || !gitPath.stdout) {
    // Not inside a git checkout (or git is unavailable). Quiet no-op.
    return 0;
  }

  const hooksDir = resolve(ROOT, gitPath.stdout.trim());
  const hookPath = resolve(hooksDir, "post-commit");

  if (existsSync(hookPath)) {
    const current = readFileSync(hookPath, "utf-8");
    if (current === HOOK_CONTENT) {
      return 0; // already installed, nothing to do
    }
    console.warn(
      `[install-git-hooks] ${hookPath} already exists with different content, leaving it alone.`,
    );
    return 0;
  }

  mkdirSync(hooksDir, { recursive: true });
  writeFileSync(hookPath, HOOK_CONTENT, "utf-8");
  chmodSync(hookPath, 0o755);
  console.log(`[install-git-hooks] installed ${hookPath}`);
  return 0;
}

process.exit(main());
