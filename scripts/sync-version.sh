#!/usr/bin/env bash
# sync-version.sh, Extract version from latest commit message (vX.Y.Z:) and update all version files.
# Called as a post-commit hook or manually.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Extract version from HEAD commit message (pattern: vX.Y.Z: ...)
VERSION=$(git log -1 --format='%s' | grep -oP '^v\K[0-9]+\.[0-9]+(\.[0-9]+)?' || true)
if [ -z "$VERSION" ]; then
  exit 0
fi

PKG="$REPO_ROOT/package.json"
TAURI="$REPO_ROOT/src-tauri/tauri.conf.json"
CARGO="$REPO_ROOT/src-tauri/Cargo.toml"
PYPROJECT="$REPO_ROOT/pyproject.toml"
GENERATED="$REPO_ROOT/src/components/dialogs/whatsNew.generated.ts"
GEN_SCRIPT="$REPO_ROOT/scripts/gen-whatsnew.mjs"

CURRENT=$(python3 - <<'PY' "$PKG"
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh)["version"])
PY
)
if [ "$CURRENT" = "$VERSION" ]; then
  exit 0
fi

python3 - <<'PY' "$VERSION" "$PKG" "$TAURI" "$CARGO" "$PYPROJECT"
import json
import re
import sys
from pathlib import Path

version, pkg_path, tauri_path, cargo_path, pyproject_path = sys.argv[1:]

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
PY

# package.json's new version is a generation input for whatsNew.generated.ts
# (scripts/gen-whatsnew.mjs). Regenerate it here so the amended commit below
# does not amend package.json's version without also amending the derived
# file, which is exactly the drift that made v0.13.24 and v0.13.25 fail
# `pnpm run sync:check` in quality-gates.
#
# gen-whatsnew.mjs exits 2 specifically when CHANGELOG.md's latest section
# does not yet mention the new version (a plain code commit whose message
# happens to carry a `vX.Y.Z:` label but adds no CHANGELOG section). That is
# not this hook's problem to fix: warn and leave the generated file
# untouched (it never got written, since the guard fires before the write),
# then continue amending the four version manifests. Any other nonzero exit
# is a real generator failure: do not swallow it, do not amend, fail loudly.
set +e
GEN_OUTPUT=$(node "$GEN_SCRIPT" 2>&1)
GEN_STATUS=$?
set -e

ADD_PATHS=("$PKG" "$TAURI" "$CARGO" "$PYPROJECT")
if [ "$GEN_STATUS" -eq 0 ]; then
  ADD_PATHS+=("$GENERATED")
elif [ "$GEN_STATUS" -eq 2 ]; then
  echo "[sync-version] warning: scripts/gen-whatsnew.mjs left whatsNew.generated.ts untouched (CHANGELOG.md has no section for v$VERSION yet):" >&2
  echo "$GEN_OUTPUT" >&2
else
  echo "[sync-version] error: scripts/gen-whatsnew.mjs failed (exit $GEN_STATUS):" >&2
  echo "$GEN_OUTPUT" >&2
  exit 1
fi

# Amend the commit to include version changes
git add "${ADD_PATHS[@]}"
git commit --amend --no-edit --no-verify
