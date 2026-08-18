#!/usr/bin/env node
/**
 * i18n-parity: verify that all locale files have the same key structure as
 * en.json, and that their What's New highlights were translated for this release.
 *
 * The structural check flattens each file, so an array is compared as
 * `whatsNewDialog.highlights.0`, `.1` and so on: it sees a differing element
 * count and an empty string, and nothing else. A locale whose highlights still
 * hold the previous release's wording has the right count and non-empty values,
 * and scripts/gen-whatsnew.mjs --check only ever looks at en.json, so that
 * locale would ship last release's notes with every gate green. The stamp check
 * below closes that: scripts/gen-whatsnew.mjs writes
 * `whatsNewDialog.highlightsStamp` into en.json as "<version>+<digest8>", where
 * the digest is a sha256 over the English bullets themselves, and every other
 * locale must carry the same value. Because the digest moves on any wording
 * edit, not only at a release boundary, matching it means someone retranslated
 * against the English text that is actually shipping.
 *
 * The authoring rules on the English bullets are enforced by
 * scripts/gen-whatsnew.mjs, which never sees a translation. The translated
 * arrays are checked here instead: no backticks, and at most 200 characters
 * (looser than the 140 imposed on English, since a translation of the same
 * sentence runs longer).
 *
 * Key parity and `v === ""` were the whole value check, and three defect classes
 * walked past it, two of them live in the shipping bundle. See the section
 * comments further down for each one:
 *   - a locale that dropped a `{{placeholder}}` and hardcoded the value
 *   - a locale whose placeholder IDENTIFIERS were translated with the prose
 *   - a key whose placeholder no CALLER supplies, which every locale renders
 *     as a literal token and no cross-locale comparison can see
 * plus a widened blank-value guard, and a ratchet on values that are still
 * byte-identical to English.
 *
 * Exit codes:
 *   0  pass
 *   1  fail (key mismatch, blank or non-string values, a placeholder set that
 *      disagrees with en, a call site that does not supply a placeholder its
 *      key needs, untranslated values above the committed baseline, a stale
 *      highlightsStamp, or a translated highlight that breaks the authoring
 *      rules)
 *
 * CI runs this as its own step (.github/workflows/ci.yml, "i18n locale parity
 * and What's New stamp"), so exit 1 fails the quality-gates job and, on a
 * release tag, skips build and release entirely. package.json exposes it as
 * `i18n:parity` and as the second half of `i18n:check`.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// A file: URL is not a path. `.pathname` keeps the leading slash a Windows URL
// carries ("/C:/repo") and leaves percent-escapes in place, so on Windows the
// joined path was relative and resolved against cwd ("C:\C:\repo\src\..."),
// and any directory with a space in its name broke everywhere. fileURLToPath is
// the conversion, and it is what every other script under scripts/ already uses.
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const LOCALES_DIR = join(ROOT, "src", "locales");
// The caller-side check below reads the call sites, so it needs src/ as well as
// src/locales/. Both hang off ROOT, which tests/scripts/script-fixture.ts
// relocates by copying this script into a throwaway repo; no test-only flag is
// added here for that.
const SRC_DIR = join(ROOT, "src");
const en = JSON.parse(readFileSync(join(LOCALES_DIR, "en.json"), "utf8"));

function flatten(obj, prefix = "") {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object") Object.assign(out, flatten(v, key));
    else out[key] = v;
  }
  return out;
}

const fe = flatten(en);
const keysE = new Set(Object.keys(fe));
console.log(`en keys: ${keysE.size}`);

let ok = true;
const localeFiles = readdirSync(LOCALES_DIR)
  .filter((f) => f.endsWith(".json") && f !== "en.json")
  .sort();

// What's New freshness stamp. en.json's value is written by
// scripts/gen-whatsnew.mjs as "<version>+<digest8>"; every other locale copies it.
const enStamp = en.whatsNewDialog?.highlightsStamp;
const staleStamps = [];

// The same idea one level down, for the per-release archive the modal reads when
// an operator skipped releases: en.json carries `releaseStamps`, a digest per
// version, and each locale copies the map. A reworded past release moves one
// digest, which names exactly the version whose translation is now behind.
const enReleaseStamps = en.whatsNewDialog?.releaseStamps ?? {};
const staleArchives = [];

// Authoring rules for the TRANSLATED bullets. gen-whatsnew.mjs applies the
// English ones (140 chars) and never reads a translation; 200 leaves room for
// a language that says the same thing in more characters.
const MAX_TRANSLATED_LENGTH = 200;

/** lang -> flattened locale, kept for the placeholder and translation checks below. */
const flatLocales = {};

for (const file of localeFiles) {
  const lang = file.replace(/\.json$/, "");
  const data = JSON.parse(readFileSync(join(LOCALES_DIR, file), "utf8"));
  const stamp = data.whatsNewDialog?.highlightsStamp;
  if (stamp !== enStamp) {
    staleStamps.push({ lang, stamp });
  }

  const checkBullets = (arr, where) => {
    if (!Array.isArray(arr)) return;
    arr.forEach((text, index) => {
      if (typeof text !== "string") return;
      if (text.includes("`")) {
        ok = false;
        console.error(
          `  ${lang} ${where}[${index}]: backtick / code identifier not allowed: ${text}`,
        );
      }
      if (text.length > MAX_TRANSLATED_LENGTH) {
        ok = false;
        console.error(
          `  ${lang} ${where}[${index}]: ${text.length} chars ` +
            `(max ${MAX_TRANSLATED_LENGTH}). The modal shows it verbatim and never truncates it: ${text}`,
        );
      }
    });
  };
  checkBullets(data.whatsNewDialog?.highlights, "whatsNewDialog.highlights");
  // The archive is rendered by the same modal, one section per release, so its
  // bullets carry the same rules as the current ones.
  for (const [version, bullets] of Object.entries(data.whatsNewDialog?.releases ?? {})) {
    checkBullets(bullets, `whatsNewDialog.releases.${version}`);
  }

  // Per-version stamps. The structural check above already forces the archive to
  // hold the same versions with the same bullet counts as en.json, but not the
  // same wording, and a past release that gets reworded in CHANGELOG.md moves
  // only its own digest. Comparing the whole map names the versions to redo.
  const localeStamps = data.whatsNewDialog?.releaseStamps ?? {};
  const behind = Object.entries(enReleaseStamps).filter(
    ([version, digest]) => localeStamps[version] !== digest,
  );
  if (behind.length) {
    staleArchives.push({ lang, versions: behind.map(([version]) => version) });
  }
  const fl = flatten(data);
  flatLocales[lang] = fl;
  const keysL = new Set(Object.keys(fl));
  const onlyEn = [...keysE].filter((k) => !keysL.has(k));
  const onlyL = [...keysL].filter((k) => !keysE.has(k));
  // Class D. `v === ""` was the whole test, so `null`, a number, a boolean and a
  // value that is nothing but whitespace all passed as translated. i18next
  // renders null and "" as the empty string and a number as its digits, so any
  // of them is a blank or wrong label on screen. No such value exists at HEAD;
  // this is the guard that keeps one from reappearing.
  const empty = Object.entries(fl)
    .filter(([, v]) => typeof v !== "string" || v.trim() === "")
    .map(([k, v]) => `${k} (${v === "" ? '""' : JSON.stringify(v)})`);
  console.log(`${lang} keys: ${keysL.size}`);
  if (onlyEn.length) {
    ok = false;
    console.error(`  en-only (missing in ${lang}): ${onlyEn.length}`);
    onlyEn.slice(0, 5).forEach((k) => console.error(`    - ${k}`));
  }
  if (onlyL.length) {
    ok = false;
    console.error(`  ${lang}-only (extra): ${onlyL.length}`);
    onlyL.slice(0, 5).forEach((k) => console.error(`    - ${k}`));
  }
  if (empty.length) {
    ok = false;
    console.error(`  ${lang} empty values: ${empty.length}`);
    empty.slice(0, 5).forEach((k) => console.error(`    - ${k}`));
  }
}

if (enStamp === undefined) {
  ok = false;
  console.error(
    "  en.json has no whatsNewDialog.highlightsStamp, so nothing can tell whether the other " +
      "locales translated the English highlights that are actually shipping. Run " +
      "`node scripts/gen-whatsnew.mjs` to write it.",
  );
} else if (staleStamps.length) {
  ok = false;
  console.error(
    `  whatsNewDialog.highlightsStamp: ${staleStamps.length} locale(s) not at en's "${enStamp}"`,
  );
  for (const { lang, stamp } of staleStamps) {
    console.error(`    - ${lang}: ${stamp === undefined ? "(key missing)" : JSON.stringify(stamp)}`);
  }
  console.error(
    "  The English whatsNewDialog.highlights changed, so those locales are showing wording that " +
      "no longer matches. The stamp is \"<version>+<sha256 of the English bullets>\", so it moves " +
      "on any edit to the English text, not only on a version bump: a mismatch means retranslate, " +
      "not merely rebuild. For each locale, translate en.json's whatsNewDialog.highlights into " +
      "that language, replacing the array element by element, then set its " +
      `whatsNewDialog.highlightsStamp to "${enStamp}". Do not copy the stamp on its own: it is ` +
      "the only signal that the translation was actually redone.",
  );
}

if (Object.keys(enReleaseStamps).length === 0) {
  ok = false;
  console.error(
    "  en.json has no whatsNewDialog.releaseStamps, so nothing can tell whether the archive the " +
      "What's New modal reads was translated. Run `node scripts/gen-whatsnew.mjs` to write it.",
  );
} else if (staleArchives.length) {
  ok = false;
  console.error(
    `  whatsNewDialog.releaseStamps: ${staleArchives.length} locale(s) behind en's archive`,
  );
  for (const { lang, versions } of staleArchives) {
    console.error(`    - ${lang}: ${versions.join(", ")}`);
  }
  console.error(
    "  The modal shows every release between the version an operator last ran and the one they " +
      "just installed, so those versions are still on screen. Translate en.json's " +
      "whatsNewDialog.releases entry for each version listed, then copy en's " +
      "whatsNewDialog.releaseStamps map. For an archive that was never filled in, " +
      "`node scripts/backfill-whatsnew-archive.mjs` recovers past translations from git history.",
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Interpolation checks
//
// Everything above compares key SETS. A key can be present in all ten locales,
// non-empty everywhere, and still render wrong, because the part that carries
// the number or the filename is the `{{placeholder}}` inside the value, and
// nothing looked at it.
// ═══════════════════════════════════════════════════════════════════════════

// i18next interpolation. `{{- name}}` is the unescaped form and `{{name, fmt}}`
// carries a formatter, so the identifier is what comes before the first comma.
const INTERPOLATION = /\{\{\s*-?\s*([^{}]*?)\s*\}\}/g;

function placeholders(value) {
  const out = new Set();
  if (typeof value !== "string") return out;
  INTERPOLATION.lastIndex = 0;
  let m;
  while ((m = INTERPOLATION.exec(value)) !== null) {
    const name = m[1].split(",")[0].trim();
    // `$t(other.key)` nesting and `{{}}` are not interpolation variables.
    if (name && !name.startsWith("$")) out.add(name);
  }
  return out;
}

const sorted = (set) => [...set].sort();

// ── Classes A and B: a locale whose placeholder set differs from en's ───────
//
// A: the locale dropped `{{seconds}}` and hardcoded a number, so the string
//    states a value the code never supplies and can no longer be right when the
//    constant moves.
// B: the locale had its placeholder IDENTIFIERS translated along with the
//    prose (`{{success}}` -> `{{Erfolg}}`). The caller passes the English name,
//    i18next finds no match, and the raw token reaches the screen.
//
// Both are the same observation from en's side: this key's placeholder set is
// not the set en declares. Only en is the reference, because en is what the
// call sites were written against.
const placeholderDiffs = [];
for (const lang of Object.keys(flatLocales)) {
  const fl = flatLocales[lang];
  for (const [key, enValue] of Object.entries(fe)) {
    if (typeof enValue !== "string") continue;
    if (!(key in fl)) continue; // already reported as a key mismatch above
    const want = placeholders(enValue);
    const got = placeholders(fl[key]);
    const missing = sorted(want).filter((p) => !got.has(p));
    const extra = sorted(got).filter((p) => !want.has(p));
    if (missing.length || extra.length) {
      placeholderDiffs.push({ lang, key, missing, extra, value: fl[key] });
    }
  }
}

if (placeholderDiffs.length) {
  ok = false;
  const langs = [...new Set(placeholderDiffs.map((d) => d.lang))];
  console.error(
    `\n  placeholder mismatch vs en: ${placeholderDiffs.length} value(s) across ${langs.length} locale(s)`,
  );
  for (const lang of langs) {
    const rows = placeholderDiffs.filter((d) => d.lang === lang);
    console.error(`    ${lang}: ${rows.length}`);
    for (const r of rows.slice(0, 8)) {
      const parts = [];
      if (r.missing.length) parts.push(`dropped {{${r.missing.join("}}, {{")}}}`);
      if (r.extra.length) parts.push(`renamed/added {{${r.extra.join("}}, {{")}}}`);
      console.error(`      - ${r.key}: ${parts.join("; ")}`);
      console.error(`        ${JSON.stringify(r.value)}`);
    }
    if (rows.length > 8) console.error(`      ... and ${rows.length - 8} more`);
  }
  console.error(
    "  A dropped placeholder means the locale hardcoded a value the code supplies, so the string " +
      "is a lie the moment that value changes. A renamed one means the identifier itself was " +
      "translated: the caller still passes the English name, so i18next cannot substitute and the " +
      "reader sees the literal token. Placeholder identifiers are code and are never translated.",
  );
}

// ── Class C: the interpolation object at the call site ─────────────────────
//
// The check above compares locales against each other, so a placeholder that
// every locale agrees on but no caller supplies is invisible to it. That is the
// stronger check and it needs the other side of the contract: the object
// literal passed to t().
//
// Covered call shapes, established by grepping src for every i18next entry
// point (`t("` 2148 hits, `t(\`` 23 hits, `i18n.t(` 1 hit, `getFixedT` 1 hit,
// `useTranslation` throughout, no `<Trans>` and no `keyPrefix` anywhere):
//   covered   t("literal.key")            and t("literal.key", { ... })
//             both the useTranslation-bound t and Home.tsx's getFixedT-bound t,
//             since both are called as a bare `t(`, and i18n.t("...") too
//   reported  t(`template.${key}`)        key not knowable statically
//   reported  t("k", opts) / t("k", {...spread}) / t("k", "fallback")
//             options not knowable statically
// The reported buckets are printed with counts and locations on every run, pass
// or fail. A gap that is not in the output is a gap nobody knows about, which is
// the same defect class this check exists to catch.
const PLURAL_SUFFIXES = ["_zero", "_one", "_two", "_few", "_many", "_other"];
// Options i18next consumes itself. They are never interpolation variables, and
// `count` is special: i18next supplies it to the interpolator implicitly for a
// plural family, so `{{count}}` in a plural value is correct and must not be
// flagged.
const RESERVED_OPTIONS = new Set([
  "count",
  "context",
  "defaultValue",
  "defaultValue_one",
  "defaultValue_other",
  "ns",
  "lng",
  "lngs",
  "fallbackLng",
  "replace",
  "returnObjects",
  "returnDetails",
  "joinArrays",
  "postProcess",
  "interpolation",
  "keySeparator",
  "nsSeparator",
  "skipInterpolation",
  "ordinal",
]);

function walkSrc(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "locales") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walkSrc(p, out);
    // Test files are excluded: they call t() with invented keys and fixture
    // options, and none of it reaches a user.
    else if (/\.(ts|tsx)$/.test(name) && !name.includes(".test.")) out.push(p);
  }
  return out;
}

/** Slice exactly one t(...) call by balancing parens, skipping string bodies. */
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
  return null;
}

/** Split an object-literal body on its top-level commas. */
function splitTopLevel(src) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let start = 0;
  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i];
    if (quote) {
      if (ch === "\\") i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") quote = ch;
    else if (ch === "{" || ch === "[" || ch === "(") depth += 1;
    else if (ch === "}" || ch === "]" || ch === ")") depth -= 1;
    else if (ch === "," && depth === 0) {
      parts.push(src.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(src.slice(start));
  return parts.map((p) => p.trim()).filter(Boolean);
}

/**
 * Property names of an object literal body, or null when any part of it is not
 * statically knowable (a spread, a computed key, anything unparsed). Returning
 * null routes the call into the reported-gap bucket instead of pretending the
 * set is complete, which would turn a spread into a false "missing variable".
 */
function objectLiteralKeys(body) {
  const out = new Set();
  for (const part of splitTopLevel(body)) {
    if (part.startsWith("...")) return null;
    const m = /^(?:(["'])([^"']+)\1|([A-Za-z_$][\w$]*))\s*(:|$)/.exec(part);
    if (!m) return null;
    out.add(m[2] ?? m[3]);
  }
  return out;
}

const T_LITERAL = /\bt\(\s*(["'])([A-Za-z0-9_.]+)\1\s*(?:,|\))/g;
const T_TEMPLATE = /\bt\(\s*`/g;

const callerMissing = [];
const dynamicKeyCalls = [];
const opaqueOptionCalls = [];
const unresolvedKeyCalls = [];

for (const file of walkSrc(SRC_DIR)) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  const text = readFileSync(file, "utf8");
  const lineOf = (index) => text.slice(0, index).split("\n").length;

  T_TEMPLATE.lastIndex = 0;
  let tm;
  while ((tm = T_TEMPLATE.exec(text)) !== null) {
    dynamicKeyCalls.push(`${rel}:${lineOf(tm.index)}`);
  }

  T_LITERAL.lastIndex = 0;
  let m;
  while ((m = T_LITERAL.exec(text)) !== null) {
    const key = m[2];
    if (!key.includes(".")) continue; // not a translation key
    const call = sliceCall(text, text.indexOf("(", m.index));
    if (call === null) continue;
    const where = `${rel}:${lineOf(m.index)}`;

    // Which en keys does this call reach? A plural family is reached through
    // its base name, so the required set is the union over the family.
    const members = [];
    if (key in fe) members.push(key);
    for (const s of PLURAL_SUFFIXES) if (`${key}${s}` in fe) members.push(`${key}${s}`);
    if (members.length === 0) {
      // i18n-lint owns "key missing from every locale". Reported here, not failed.
      unresolvedKeyCalls.push(`${where}: ${key}`);
      continue;
    }
    const isPluralFamily =
      members.some((k) => k !== key) || PLURAL_SUFFIXES.some((s) => key.endsWith(s));

    const required = new Set();
    for (const k of members) for (const p of placeholders(fe[k])) required.add(p);
    // i18next passes `count` to the interpolator itself for a plural family.
    if (isPluralFamily) required.delete("count");
    if (required.size === 0) continue;

    // Second argument, if any.
    const argsMatch = /^\(\s*(["'])[A-Za-z0-9_.]+\1\s*([\s\S]*)\)\s*$/.exec(call);
    const rest = (argsMatch ? argsMatch[2] : "").trim();

    let provided;
    if (rest === "") {
      provided = new Set();
    } else if (rest.startsWith(",")) {
      const opts = rest.slice(1).trim();
      if (opts.startsWith("{") && opts.endsWith("}")) {
        provided = objectLiteralKeys(opts.slice(1, -1));
        if (provided === null) {
          opaqueOptionCalls.push(`${where}: ${key} (spread or computed key)`);
          continue;
        }
      } else {
        opaqueOptionCalls.push(`${where}: ${key} (options not an object literal)`);
        continue;
      }
    } else {
      opaqueOptionCalls.push(`${where}: ${key} (unparsed call shape)`);
      continue;
    }

    const missing = sorted(required).filter((p) => !provided.has(p));
    if (missing.length) {
      callerMissing.push({
        where,
        key,
        missing,
        provided: sorted(provided).filter((p) => !RESERVED_OPTIONS.has(p)),
        value: fe[members[0]],
      });
    }
  }
}

if (callerMissing.length) {
  ok = false;
  console.error(
    `\n  call site does not supply a placeholder the key needs: ${callerMissing.length}`,
  );
  for (const r of callerMissing) {
    console.error(`    - ${r.where}  ${r.key}`);
    console.error(`        en: ${JSON.stringify(r.value)}`);
    console.error(
      `        needs {{${r.missing.join("}}, {{")}}}, call passes ` +
        (r.provided.length ? `{ ${r.provided.join(", ")} }` : "nothing"),
    );
  }
  console.error(
    "  Every locale renders the token literally, so no cross-locale comparison can see this. " +
      "Either the call was migrated to a new variable name and the string was not, or the " +
      "string gained a placeholder the caller never learned about. Fix whichever side is wrong, " +
      "and check the sibling keys around it: this kind of half-finished rename leaves the " +
      "migrated and unmigrated versions side by side.",
  );
}

// Coverage, printed on every run. These are the call shapes this check cannot
// resolve statically. They are not failures and they are not silence either.
console.log(
  `t() call-site coverage: ${dynamicKeyCalls.length} dynamic-key call(s), ` +
    `${opaqueOptionCalls.length} call(s) with options this check cannot read, ` +
    `${unresolvedKeyCalls.length} key(s) not in en.json (i18n-lint owns those). ` +
    "Test files are not scanned.",
);
for (const c of dynamicKeyCalls) console.log(`  dynamic key: ${c}`);
for (const c of opaqueOptionCalls) console.log(`  opaque options: ${c}`);
for (const c of unresolvedKeyCalls) console.log(`  unresolved key: ${c}`);

// ── Class E: values that are byte-identical to English ─────────────────────
//
// This is not a broken string, it is untranslated work, and there are thousands
// of them. Failing on the stock would leave CI red until somebody translates the
// whole bundle, which is not a change anyone can land, so the existing debt is
// reported and does not block. What does block is GROWTH: the per-locale counts
// below are a committed ratchet, and a locale above its number fails. That way a
// new key shipped with the English text pasted into all ten files is caught on
// the commit that adds it, which is the only moment it is cheap to fix.
//
// The baseline lives in this file rather than a side-car data file on purpose:
// raising it is a diff to the gate itself, in the review of the change that
// needed it raised, instead of a quiet edit to a generated JSON blob nobody
// reads. Lowering it is encouraged and the run prints the new number.
//
// Scope: values containing whitespace, so single-token values (product names,
// "OK", "%s", units, language endonyms) do not count as untranslated. A locale
// legitimately identical to English on a whole sentence is rare enough to spend
// a baseline slot on.
const UNTRANSLATED_BASELINE = {
  de: 556,
  es: 548,
  fr: 544,
  ja: 617,
  ko: 151,
  "pt-BR": 550,
  ru: 659,
  "zh-CN": 610,
  "zh-TW": 610,
};

const isProse = (v) => typeof v === "string" && v.trim() !== "" && /\s/.test(v.trim());
const untranslated = {};
for (const lang of Object.keys(flatLocales)) {
  const fl = flatLocales[lang];
  untranslated[lang] = Object.keys(fe).filter(
    (k) => isProse(fe[k]) && fl[k] === fe[k],
  );
}

{
  const overBudget = [];
  const underBudget = [];
  console.log("\nuntranslated (value byte-identical to en, whitespace-bearing values only):");
  for (const lang of Object.keys(untranslated).sort()) {
    const n = untranslated[lang].length;
    // A locale with no entry is budgeted at zero, so a new locale committed as a
    // copy of en.json fails on the commit that adds it rather than passing on the
    // strength of not being listed.
    const budget = UNTRANSLATED_BASELINE[lang] ?? 0;
    const known = lang in UNTRANSLATED_BASELINE;
    const delta = n - budget;
    console.log(
      `  ${lang}: ${n} / baseline ${budget}${known ? "" : " (no baseline entry)"}` +
        (delta > 0 ? `  (+${delta})` : delta < 0 ? `  (${delta})` : ""),
    );
    if (delta > 0) overBudget.push({ lang, n, budget, known });
    else if (delta < 0) underBudget.push({ lang, n });
  }
  if (overBudget.length) {
    ok = false;
    for (const { lang, n, budget, known } of overBudget) {
      console.error(
        `  ${lang}: ${n} untranslated value(s), baseline ${budget}` +
          (known ? "" : " (no entry in UNTRANSLATED_BASELINE)") +
          `. ${n - budget} more than the committed number.`,
      );
      for (const k of untranslated[lang].slice(0, 20)) console.error(`    - ${k}`);
      if (n > 20) console.error(`    ... ${n - 20} more`);
    }
    console.error(
      "  Translate them, or, if the English really is the right value in this language, raise " +
        "that locale's number in UNTRANSLATED_BASELINE in scripts/i18n-parity.mjs and say why in " +
        "the commit message. The baseline sits in the gate itself so that raising it is a diff a " +
        "reviewer sees, which is the whole mechanism: existing debt does not block, growth does.",
    );
  }
  if (underBudget.length) {
    console.log(
      "  baseline can be tightened: " +
        underBudget.map(({ lang, n }) => `${lang}: ${n}`).join(", "),
    );
  }
}

console.log(ok ? "i18n-parity: ok" : "i18n-parity: FAIL");
process.exit(ok ? 0 : 1);
