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

CURRENT=$(grep -oP '"version":\s*"\K[^"]+' "$PKG" | head -1)
if [ "$CURRENT" = "$VERSION" ]; then
  exit 0
fi

# Update all three files
sed -i "s/\"version\": \"$CURRENT\"/\"version\": \"$VERSION\"/" "$PKG"
sed -i "s/\"version\": \"$CURRENT\"/\"version\": \"$VERSION\"/" "$TAURI"
sed -i "s/^version = \"$CURRENT\"/version = \"$VERSION\"/" "$CARGO"

# Amend the commit to include version changes
git add "$PKG" "$TAURI" "$CARGO"
git commit --amend --no-edit --no-verify
