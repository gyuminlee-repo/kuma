#!/usr/bin/env bash
# Point git at the tracked .githooks directory so every clone shares the same hooks.
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
git config core.hooksPath .githooks
chmod +x .githooks/*
echo "git core.hooksPath -> .githooks"
echo "active hooks:"
ls -1 .githooks
