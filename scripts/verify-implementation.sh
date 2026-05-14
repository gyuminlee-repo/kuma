#!/usr/bin/env bash
# Post-implementation verification harness for spec 2026-05-13-export-all-macrogen.
# Run after both Part A and Part B agents complete.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

pass() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAILED=1; }
FAILED=0

echo "== A. Python backend =="
python3 -m pytest tests/test_macrogen_export.py -v 2>&1 | tail -20 && pass "macrogen exporter tests" || fail "macrogen exporter tests"
python3 -m pytest tests/test_export_models.py -v 2>&1 | tail -10 && pass "pydantic model tests" || fail "pydantic model tests"

echo "== B. Frontend typecheck =="
if command -v npx >/dev/null; then
  npx tsc --noEmit 2>&1 | tail -20 && pass "tsc --noEmit" || fail "tsc --noEmit"
else
  echo "  (skip: npx unavailable)"
fi

echo "== C. Frontend tests =="
if command -v pnpm >/dev/null; then
  pnpm vitest run 2>&1 | tail -30 && pass "vitest" || fail "vitest"
else
  echo "  (skip: pnpm unavailable)"
fi

echo "== D. Cross-layer sync =="
if command -v pnpm >/dev/null && [ -f .cross-layer-sync.json ]; then
  pnpm sync:check 2>&1 | tail -10 && pass "sync:check" || fail "sync:check"
fi

echo "== E. Spec coverage =="
for term in "export_macrogen_xls" "ExportMacrogenParams" "ExportAllParams" "handle_export_macrogen" "handle_export_all" "handleExportAll" "ResizeHandle" "layoutSlice" "SIDEBAR_DEFAULT_WIDTH"; do
  if grep -rq "$term" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.mjs" src kuma_core python-core scripts 2>/dev/null; then
    pass "$term defined"
  else
    fail "$term missing"
  fi
done

echo "== F. Removed legacy =="
for term in "MappingExportDialog" "handleExportMappingWithParams"; do
  if grep -rq "$term" --include="*.tsx" --include="*.ts" src 2>/dev/null; then
    fail "$term still referenced"
  else
    pass "$term removed"
  fi
done

echo
[ "$FAILED" = "0" ] && { echo "ALL PASS"; exit 0; } || { echo "SOME FAILED"; exit 1; }
