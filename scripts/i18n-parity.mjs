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
 * Exit codes:
 *   0  pass
 *   1  fail (key mismatch, empty values, a stale highlightsStamp, or a
 *      translated highlight that breaks the authoring rules)
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// A file: URL is not a path. `.pathname` keeps the leading slash a Windows URL
// carries ("/C:/repo") and leaves percent-escapes in place, so on Windows the
// joined path was relative and resolved against cwd ("C:\C:\repo\src\..."),
// and any directory with a space in its name broke everywhere. fileURLToPath is
// the conversion, and it is what every other script under scripts/ already uses.
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LOCALES_DIR = join(ROOT, "src", "locales");
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
  const keysL = new Set(Object.keys(fl));
  const onlyEn = [...keysE].filter((k) => !keysL.has(k));
  const onlyL = [...keysL].filter((k) => !keysE.has(k));
  const empty = Object.entries(fl).filter(([, v]) => v === "").map(([k]) => k);
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

console.log(ok ? "i18n-parity: ok" : "i18n-parity: FAIL");
process.exit(ok ? 0 : 1);
