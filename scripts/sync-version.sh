#!/usr/bin/env bash
# sync-version.sh, Extract version from latest commit message (vX.Y.Z:) and update all version files.
# Called as a post-commit hook or manually.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Extract version from HEAD commit message (pattern: vX.Y.Z: ...)
#
# POSIX sed rather than `grep -oP`, which exists only in GNU grep: on macOS the
# BSD grep rejected -P, `|| true` swallowed the error, and the version stayed
# empty, so every bump made on a Mac skipped this script without saying so.
#
# The capture takes two or three components on purpose and drops a fourth. The
# commit convention is vA.BB.CC.DD, but Tauri and Cargo enforce SemVer 2.0
# MAJOR.MINOR.PATCH (scripts/rename-bundle-to-tag.mjs states the rule), so the
# files rewritten below hold three parts and the DD suffix belongs to the tag and
# to bundle file names. Widening this pattern would put a four-part string into
# package.json and Cargo.toml, which is the opposite of the fix. What the
# truncation must NOT do is make a DD release look like a no-op: v0.16.25.1
# yields 0.16.25, package.json already says 0.16.25, and the equality below used
# to `exit 0` there, which skipped the What's New regeneration and shipped
# v0.16.25.1 bullets stamped as v0.16.25 across all ten locales with every gate
# green. The version files are unchanged in that case; the derived release notes
# are not, so the generator still runs (see VERSION_CHANGED below).
VERSION=$(git log -1 --format='%s' |
  sed -n 's/^v\([0-9][0-9]*\.[0-9][0-9]*\(\.[0-9][0-9]*\)\{0,1\}\).*/\1/p')
if [ -z "$VERSION" ]; then
  exit 0
fi

PKG="$REPO_ROOT/package.json"
TAURI="$REPO_ROOT/src-tauri/tauri.conf.json"
CARGO="$REPO_ROOT/src-tauri/Cargo.toml"
PYPROJECT="$REPO_ROOT/pyproject.toml"
LOCK="$REPO_ROOT/src-tauri/Cargo.lock"
# kuma_core/shared/version.py stamps KUMA_VERSION into every .run.json, every
# hidden __kuma_meta__ sheet and every MAME run report, and
# .cross-layer-sync.json now checks it alongside the five release manifests, so leaving
# it out here would fail `pnpm run sync:check` on every bump.
VERSION_PY="$REPO_ROOT/kuma_core/shared/version.py"
LOCALE_EN="$REPO_ROOT/src/locales/en.json"
GEN_SCRIPT="$REPO_ROOT/scripts/gen-whatsnew.mjs"

CURRENT=$(python3 - <<'PY' "$PKG"
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh)["version"])
PY
)
VERSION_CHANGED=1
if [ "$CURRENT" = "$VERSION" ]; then
  VERSION_CHANGED=0
fi

if [ "$VERSION_CHANGED" -eq 1 ]; then
python3 - <<'PY' "$VERSION" "$PKG" "$TAURI" "$CARGO" "$PYPROJECT" "$VERSION_PY"
import json
import re
import sys
from pathlib import Path

version, pkg_path, tauri_path, cargo_path, pyproject_path, version_py_path = sys.argv[1:]

for json_path in (pkg_path, tauri_path):
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

for toml_path in (cargo_path, pyproject_path):
    path = Path(toml_path)
    content = path.read_text(encoding="utf-8")
    updated = re.sub(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{version}"', content, count=1)
    if updated == content:
        raise SystemExit(f"Failed to update version in {toml_path}")
    path.write_text(updated, encoding="utf-8")

# KUMA_VERSION only. KURO_MODULE_VERSION sits on the next line and names the
# KURO export contract rather than the release, so the pattern is anchored to
# the constant name and rewrites exactly one line.
version_py = Path(version_py_path)
content = version_py.read_text(encoding="utf-8")
updated, count = re.subn(r'(?m)^KUMA_VERSION = "[^"]+"', f'KUMA_VERSION = "{version}"', content, count=1)
if count != 1:
    raise SystemExit(f"Failed to update KUMA_VERSION in {version_py_path}")
version_py.write_text(updated, encoding="utf-8")
PY
fi

# Cargo.lock pins the kuma package version alongside Cargo.toml, and
# .cross-layer-sync.json now checks it, so a manifest-only amend would break
# `pnpm run sync:check` on every bump. `cargo update -p kuma` rewrites just the
# kuma entry and leaves every other dependency pin as recorded.
#
# --offline is deliberate and not retried online. A post-commit hook must not
# stall on the network, and an offline failure means the lockfile needs more
# than a version bump, which a person has to look at. An automatic online retry
# would turn that signal into a silent dependency pin change, the exact drift
# this script exists to prevent.
LOCK_CHANGED=0
if [ "$VERSION_CHANGED" -eq 0 ]; then
  : # the three-part version did not move, so the lockfile pin is already right
elif command -v cargo >/dev/null 2>&1; then
  set +e
  LOCK_OUTPUT=$(cargo update -p kuma --offline --manifest-path "$CARGO" 2>&1)
  LOCK_STATUS=$?
  set -e
  if [ "$LOCK_STATUS" -ne 0 ]; then
    echo "[sync-version] error: cargo update -p kuma failed (exit $LOCK_STATUS):" >&2
    echo "$LOCK_OUTPUT" >&2
    echo "[sync-version] the version files are already edited in the working tree, but the commit was NOT amended. Fix src-tauri/Cargo.lock manually, then run: node scripts/gen-whatsnew.mjs && git add package.json src-tauri/tauri.conf.json src-tauri/Cargo.toml pyproject.toml src-tauri/Cargo.lock kuma_core/shared/version.py src/locales/en.json && git commit --amend --no-edit --no-verify" >&2
    exit 1
  fi
  if ! git diff --quiet -- "$LOCK"; then
    LOCK_CHANGED=1
  fi
else
  echo "[sync-version] warning: cargo not found, so src-tauri/Cargo.lock keeps its old kuma version while the manifests move to v$VERSION. That drift fails the version-sync check in \`pnpm run sync:check\`." >&2
  echo "[sync-version] on a machine with cargo, run: cargo update -p kuma --offline --manifest-path src-tauri/Cargo.toml && git add src-tauri/Cargo.lock && git commit --amend --no-edit --no-verify" >&2
fi

# scripts/gen-whatsnew.mjs rewrites `whatsNewDialog.highlights` and its stamp in
# src/locales/en.json from the latest CHANGELOG.md "### Highlights" block.
# Regenerate it here so the amended commit below does not amend package.json's
# version without also amending the derived highlights, which is exactly the
# drift that made v0.13.24 and v0.13.25 fail `pnpm run sync:check` in
# quality-gates.
#
# This runs unconditionally, including when the three-part version did not move.
# A DD release (v0.16.25.1 on top of 0.16.25) leaves every version file alone and
# is still a different release with different notes, so the generator is what
# decides whether anything changed. Returning early on `CURRENT = VERSION`, as
# this script used to, is how v0.16.25.1 shipped its bullets under the 0.16.25
# stamp in all ten locales. The generator identifies the release by the CHANGELOG
# heading, not by package.json, so it sees the difference this comparison cannot.
#
# Only en.json is generated. The nine other src/locales/*.json highlights arrays
# are hand-translated, so a release that changes the bullets still needs a manual
# translation pass, plus the matching whatsNewDialog.highlightsStamp on each
# locale. That stamp is "<version>+<digest8>", the version followed by a sha256
# over the English bullets, so editing the wording inside one version moves it
# too and the nine translations are caught the same way a version bump catches
# them. `pnpm sync:check` does NOT catch a missed pass: its three stages
# are sync-check.mjs, sync-check-groups.mjs and gen-whatsnew.mjs --check, and the
# last of those reads en.json alone. The check that reads all ten locales is
# scripts/i18n-parity.mjs, run by `pnpm i18n:check` locally and by CI
# (.github/workflows/ci.yml, .github/workflows/build.yml).
#
# gen-whatsnew.mjs exits 2 when CHANGELOG.md's latest section is not ready for
# this release: it does not mention the new version, or it has no
# "### Highlights" block, or that block has no bullets (a plain code commit whose
# message happens to carry a `vX.Y.Z:` label but adds no CHANGELOG section hits
# the first case). That is not this hook's problem to fix: warn and leave
# en.json untouched (it never got written, since the guard fires before the
# write), then continue amending the version files.
#
# Exit 1 is the loud case, and it is now reachable from a CHANGELOG typo as well
# as from a broken generator: a "### Highlights" bullet over 140 characters, one
# carrying a backtick, one prefixed `vX.Y.Z:`, or more than five of them all fail
# there, because those bullets are shown verbatim in the modal and are never
# truncated. Do not swallow it, do not amend, fail loudly, and print how to get
# back to a good state.
set +e
GEN_OUTPUT=$(node "$GEN_SCRIPT" 2>&1)
GEN_STATUS=$?
set -e

ADD_PATHS=()
if [ "$VERSION_CHANGED" -eq 1 ]; then
  ADD_PATHS=("$PKG" "$TAURI" "$CARGO" "$PYPROJECT" "$VERSION_PY")
fi
if [ "$LOCK_CHANGED" -eq 1 ]; then
  ADD_PATHS+=("$LOCK")
fi
# On the DD path the generator runs and usually rewrites nothing, so stage
# en.json only when it actually moved. Staging an unchanged file would amend the
# commit for no reason on every commit whose subject carries a vX.Y.Z label.
if [ "$GEN_STATUS" -eq 0 ]; then
  if ! git diff --quiet -- "$LOCALE_EN"; then
    ADD_PATHS+=("$LOCALE_EN")
  fi
elif [ "$GEN_STATUS" -eq 2 ]; then
  echo "[sync-version] warning: scripts/gen-whatsnew.mjs left src/locales/en.json untouched (CHANGELOG.md has no ready '### Highlights' section for v$VERSION yet):" >&2
  echo "$GEN_OUTPUT" >&2
else
  echo "[sync-version] error: scripts/gen-whatsnew.mjs failed (exit $GEN_STATUS):" >&2
  echo "$GEN_OUTPUT" >&2
  echo "[sync-version] any version files this run edited are in the working tree (none, if the three-part version did not move), but the commit was NOT amended and src/locales/en.json was not regenerated, so nothing is lost by fixing this and rerunning." >&2
  echo "[sync-version] read the message above first: an authoring complaint means the '### Highlights' bullets in the v$VERSION CHANGELOG.md section break a rule (at most 5 bullets, at most 140 characters each, no backticks, no 'vX.Y.Z:' prefix), so rewrite the offending bullet in CHANGELOG.md. Anything else is a generator or environment fault." >&2
  echo "[sync-version] then run: node scripts/gen-whatsnew.mjs && git add package.json src-tauri/tauri.conf.json src-tauri/Cargo.toml pyproject.toml src-tauri/Cargo.lock kuma_core/shared/version.py src/locales/en.json CHANGELOG.md && git commit --amend --no-edit --no-verify" >&2
  exit 1
fi

# Amend the commit to include version changes. Nothing to stage means nothing
# moved (the common DD case where the release notes were already generated), and
# an empty `git add` under `set -u` would abort rather than do nothing.
if [ ${#ADD_PATHS[@]} -eq 0 ]; then
  exit 0
fi
git add "${ADD_PATHS[@]}"
git commit --amend --no-edit --no-verify
