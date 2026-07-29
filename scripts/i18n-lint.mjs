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

// ── English-in-UI check (scoped: MAME components) ────────────────────────────
// i18n-lint historically caught only hardcoded *Korean*; user-facing English in
// MAME UI slipped through. Flag natural-language English in high-signal
// attributes (label/helperText/stateLabel/aria-label/title) so new untranslated
// copy trips CI. Scope is all MAME components, and technical API labels
// (snake_case identifiers, unit-bearing labels like "(nt)"/"(°C)") are exempt —
// to avoid false positives on intentional code identifiers. The lookbehind
// keeps "aria-label" from also matching its "label" suffix.
const MAME_DIR = join(SRC, "components", "mame");
const ENGLISH_ATTR =
  /(?<![\w-])(label|helperText|stateLabel|aria-label|title)\s*=\s*"([^"]+)"/g;
const TECHNICAL = /_|\((?:nt|bp|°C)\)/;
const englishOffenders = [];
for (const file of walk(MAME_DIR)) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((ln, i) => {
    const trimmed = ln.trim();
    if (!trimmed || LINE_COMMENT.test(trimmed) || JSX_COMMENT.test(trimmed)) return;
    let m;
    ENGLISH_ATTR.lastIndex = 0;
    while ((m = ENGLISH_ATTR.exec(ln)) !== null) {
      const val = m[2];
      // Natural-language English heuristic: contains a space and a lowercase letter.
      if (!/ /.test(val) || !/[a-z]/.test(val)) continue;
      if (TECHNICAL.test(val)) continue;
      englishOffenders.push(`${rel}:${i + 1}: ${m[1]}="${val}"`);
    }
  });
}

// ---------------------------------------------------------------------------
// Missing-key check
//
// i18next prints the key itself when it cannot resolve one, so a key that no
// locale defines reaches the user as a raw string like
// "onboarding.maximizeHint". i18n-parity only compares locale files against
// each other, so a key that every locale is missing passes it. This walks the
// literal t("...") call sites instead and resolves them against every locale.
//
// Skipped: calls that pass a defaultValue or a literal fallback, which render
// that text rather than the key. Plural keys are matched through their CLDR
// suffixes.
// ---------------------------------------------------------------------------
const PLURAL_SUFFIXES = ["", "_zero", "_one", "_two", "_few", "_many", "_other"];
const T_CALL = /\bt\(\s*["']([A-Za-z0-9_.]+)["']\s*(,|\))/g;

function loadLocales() {
  const dir = join(SRC, "locales");
  const out = {};
  for (const f of readdirSync(dir)) {
    if (!f.endsWith(".json")) continue;
    out[f.replace(/\.json$/, "")] = JSON.parse(readFileSync(join(dir, f), "utf8"));
  }
  return out;
}

function resolves(bundle, key) {
  return PLURAL_SUFFIXES.some((suffix) => {
    let cur = bundle;
    for (const part of (key + suffix).split(".")) {
      if (cur == null || typeof cur !== "object" || !(part in cur)) return false;
      cur = cur[part];
    }
    return typeof cur === "string";
  });
}

/**
 * Slice exactly one t(...) call.
 *
 * A fixed-width window is wrong here: it runs past the closing paren into the
 * next call, so one neighbour carrying a defaultValue silently excuses every
 * call around it. Balance the parens instead, skipping string and template
 * literals so a paren inside a message does not end the scan early.
 */
function sliceCall(text, openParen) {
  let depth = 0;
  let quote = null;
  for (let i = openParen; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === "(") depth += 1;
    else if (ch === ")") {
      depth -= 1;
      if (depth === 0) return text.slice(openParen, i + 1);
    }
  }
  return text.slice(openParen, openParen + 260);
}

const locales = loadLocales();
const localeNames = Object.keys(locales);
const missingKeys = [];

for (const file of walk(SRC)) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  const text = readFileSync(file, "utf8");
  let m;
  T_CALL.lastIndex = 0;
  while ((m = T_CALL.exec(text)) !== null) {
    const key = m[1];
    if (!key.includes(".")) continue;
    const call = sliceCall(text, text.indexOf("(", m.index));
    const hasFallback =
      /defaultValue/.test(call) ||
      /^\(\s*["'][^"']+["']\s*,\s*["'][^"']{2,}["']\s*\)$/.test(call);
    if (hasFallback) continue;
    const absent = localeNames.filter((name) => !resolves(locales[name], key));
    if (absent.length === localeNames.length) {
      const line = text.slice(0, m.index).split("\n").length;
      missingKeys.push(`${rel}:${line}: ${key}`);
    }
  }
}

if (offenders.length === 0 && englishOffenders.length === 0 && missingKeys.length === 0) {
  console.log(
    "i18n-lint: ok (0 hardcoded Korean lines, 0 hardcoded English in MAME components, 0 unresolved t() keys)",
  );
  process.exit(0);
}

if (offenders.length > 0) {
  console.error(`i18n-lint: ${offenders.length} hardcoded Korean line(s) found:`);
  for (const o of offenders) console.error("  " + o);
}
if (englishOffenders.length > 0) {
  console.error(
    `i18n-lint: ${englishOffenders.length} hardcoded English string(s) in MAME components:`,
  );
  for (const o of englishOffenders) console.error("  " + o);
}
if (missingKeys.length > 0) {
  console.error(
    `i18n-lint: ${missingKeys.length} t() key(s) missing from every locale (would render as the raw key):`,
  );
  for (const o of missingKeys) console.error("  " + o);
}
console.error("\nFix: extract to src/locales/{en,ko}.json and use t() / i18next.t().");
console.error("Allowlist intentional Korean in scripts/i18n-lint.mjs ALLOWLIST.");
process.exit(1);
