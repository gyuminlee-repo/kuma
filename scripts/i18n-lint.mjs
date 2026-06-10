#!/usr/bin/env node
/**
 * i18n-lint — Detect hardcoded Korean in src/ outside locales/.
 *
 * Exit codes:
 *   0  pass (no hardcoded Korean except allowlist)
 *   1  fail (hardcoded Korean found)
 *
 * Allowlist: src/components/ui/LocaleToggle.tsx — `ko: "한국어"` self-label.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SRC = join(ROOT, "src");
const KOREAN = /[가-힯]/;
const JSX_COMMENT = /^\s*\{\s*\/\*.*\*\/\s*\}\s*$/;
const LINE_COMMENT = /^\s*(\/\/|\*|\/\*)/;

const ALLOWLIST = {
  "src/components/ui/LocaleToggle.tsx": new Set([20]),
  // 한국어 주석 — JSX comment이므로 i18n 처리 불필요
  "src/components/mame/panels/BarcodeSetupPanel.tsx": new Set([304, 305]),
  // language endonym — conventionally untranslated in language pickers
  "src/components/layout/MenuBar.tsx": new Set([74]),
  "src/components/mame/layout/MenuBar.tsx": new Set([72]),
};

function isAllowlistedLine(rel, n, line) {
  if ((ALLOWLIST[rel] || new Set()).has(n)) return true;
  if (
    /ko:\s*"한국어"/.test(line) &&
    (rel === "src/components/ui/LocaleToggle.tsx" || rel.endsWith("/MenuBar.tsx"))
  ) {
    return true;
  }
  if (
    rel === "src/components/steps/ExportFormatSelector.tsx" &&
    line.includes("PROJECT_NAME_RE")
  ) {
    return true;
  }
  return false;
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      if (name === "locales" || name === "node_modules") continue;
      walk(p, out);
    } else if (/\.(ts|tsx)$/.test(name) && !name.includes(".test.")) {
      out.push(p);
    }
  }
  return out;
}

const offenders = [];
for (const file of walk(SRC)) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  const lines = readFileSync(file, "utf8").split("\n");
  let inBlockComment = false;
  lines.forEach((ln, i) => {
    const n = i + 1;
    const trimmed = ln.trim();
    if (!trimmed) return;

    if (inBlockComment) {
      if (trimmed.includes("*/")) inBlockComment = false;
      return;
    }
    if (trimmed.startsWith("/*") || trimmed.startsWith("{/*")) {
      if (!trimmed.includes("*/")) inBlockComment = true;
      return;
    }
    if (LINE_COMMENT.test(trimmed)) return;
    if (JSX_COMMENT.test(trimmed)) return;
    if (isAllowlistedLine(rel, n, ln)) return;
    if (KOREAN.test(ln)) {
      offenders.push(`${rel}:${n}: ${trimmed.slice(0, 140)}`);
    }
  });
}

if (offenders.length === 0) {
  console.log("i18n-lint: ok (0 hardcoded Korean lines)");
  process.exit(0);
}

console.error(`i18n-lint: ${offenders.length} hardcoded Korean line(s) found:`);
for (const o of offenders) console.error("  " + o);
console.error("\nFix: extract to src/locales/{en,ko}.json and use t() / i18next.t().");
console.error("Allowlist intentional Korean in scripts/i18n-lint.mjs ALLOWLIST.");
process.exit(1);
