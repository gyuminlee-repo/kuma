#!/usr/bin/env bash
# wt-session.sh — start an isolated git-worktree session off `main`, then run a
# command inside it. This is the launcher-level way to make work happen in a
# worktree by default; a settings.json hook cannot relocate a live session's cwd.
#
# Worktrees live under .claude/worktrees/<branch-slug>/ (already git-ignored from
# CLAUDE.md context loading via ~/.claude claudeMdExcludes).
#
# Usage:
#   scripts/wt-session.sh                      # new branch wt/<timestamp>, drop into $SHELL
#   scripts/wt-session.sh feat/my-thing        # use/create branch, drop into $SHELL
#   scripts/wt-session.sh feat/my-thing -- claude --resume   # run a command in the worktree
#
# To make it your default launch path, alias your agent/editor start command, e.g.:
#   alias kuma-dev='scripts/wt-session.sh "" -- claude'
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
branch="${1:-}"
[ "$#" -gt 0 ] && shift || true
[ "${1:-}" = "--" ] && shift || true   # tolerate an explicit `--` separator

# Default to a timestamped throwaway branch when none is given.
[ -z "$branch" ] && branch="wt/$(date +%Y%m%d-%H%M%S)"

slug="${branch//\//-}"
wt="$repo/.claude/worktrees/$slug"

# Base new branches on the freshest main (best-effort; offline is fine).
git -C "$repo" fetch origin main --quiet 2>/dev/null || true

if [ -d "$wt" ]; then
  echo "Reusing worktree: $wt [$branch]"
elif git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" worktree add "$wt" "$branch"
else
  # New branch off origin/main when available, else local main.
  base="main"
  git -C "$repo" show-ref --verify --quiet refs/remotes/origin/main && base="origin/main"
  git -C "$repo" worktree add -b "$branch" "$wt" "$base"
fi

cd "$wt"
echo "→ working in $wt  [$(git -C "$wt" branch --show-current)]"

if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec "${SHELL:-/bin/bash}"
fi
