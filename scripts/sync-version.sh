#!/usr/bin/env bash
# sync-version.sh — Extract version from latest commit message (vX.Y.Z:) and update all version files.
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

# Amend the commit to include version changes
git add "$PKG" "$TAURI" "$CARGO" "$PYPROJECT"
git commit --amend --no-edit --no-verify
