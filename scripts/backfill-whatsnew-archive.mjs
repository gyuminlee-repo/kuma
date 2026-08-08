#!/usr/bin/env node
/**
 * backfill-whatsnew-archive.mjs
 *
 * Fills `whatsNewDialog.releases` in the nine translated locale files from what
 * those files themselves said at the time each release shipped.
 *
 * The What's New modal shows every release between the version an operator last
 * ran and the one they just installed, so each locale needs the bullets of past
 * releases and not only of the current one. Those translations were written once
 * already: every release overwrote `whatsNewDialog.highlights` in all ten locales
 * and `whatsNewDialog.highlightsStamp` recorded which version the wording
 * belonged to. Walking the commit history of one locale file and reading that
 * pair back recovers the archive exactly as it was translated, so nothing here
 * translates anything or asks anyone to.
 *
 * en.json is the reference and is never harvested: scripts/gen-whatsnew.mjs
 * generates it from CHANGELOG.md, and its version list and per-version bullet
 * count are what every other locale must match, because scripts/i18n-parity.mjs
 * compares flattened key sets and `releases.0.16.9.2` is a key. A version whose
 * translation cannot be recovered, or whose recovered translation has a
 * different number of bullets than the English (the CHANGELOG section was
 * reworded after that release), falls back to the English text and is reported.
 * A visible English bullet is a translation someone can fix; a missing key fails
 * the build for everyone.
 *
 * This is a repair tool rather than part of the release flow. Running it again
 * is safe and rewrites the archive from history each time. Ordinary releases add
 * their entry through `pnpm gen:whatsnew` plus a hand translation, exactly as
 * before.
 *
 * Usage:
 *   node scripts/backfill-whatsnew-archive.mjs           # write the locale files
 *   node scripts/backfill-whatsnew-archive.mjs --dry-run # report only
 */
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LOCALES_DIR = join(ROOT, "src", "locales");
const DRY_RUN = process.argv.includes("--dry-run");

function git(args) {
  return execFileSync("git", args, { cwd: ROOT, maxBuffer: 1 << 28, encoding: "utf-8" });
}

/**
 * version -> the highlights this locale carried while that version was current.
 *
 * Commits are walked newest first and the first reading for a version wins, so a
 * wording that was corrected within a release contributes its final form, which
 * is the one that shipped.
 */
function harvest(lang) {
  const path = `src/locales/${lang}.json`;
  const commits = git(["log", "--format=%H", "--", path]).trim().split("\n").filter(Boolean);
  const found = new Map();
  for (const sha of commits) {
    let dialog;
    try {
      dialog = JSON.parse(git(["show", `${sha}:${path}`]))?.whatsNewDialog;
    } catch {
      continue;
    }
    if (!dialog || !Array.isArray(dialog.highlights) || dialog.highlights.length === 0) continue;
    if (typeof dialog.highlightsStamp !== "string") continue;
    const version = dialog.highlightsStamp.split("+")[0];
    if (!version || found.has(version)) continue;
    if (!dialog.highlights.every((v) => typeof v === "string" && v.length > 0)) continue;
    found.set(version, dialog.highlights);
  }
  return found;
}

const en = JSON.parse(readFileSync(join(LOCALES_DIR, "en.json"), "utf8"));
const enReleases = en.whatsNewDialog?.releases;
const enStamps = en.whatsNewDialog?.releaseStamps;
if (!enReleases || !enStamps) {
  console.error(
    "[backfill-whatsnew] en.json has no whatsNewDialog.releases. Run `node scripts/gen-whatsnew.mjs` first.",
  );
  process.exit(1);
}
const versions = Object.keys(enReleases);

const files = readdirSync(LOCALES_DIR)
  .filter((f) => f.endsWith(".json") && f !== "en.json")
  .sort();

let fallbackTotal = 0;
for (const file of files) {
  const lang = file.replace(/\.json$/, "");
  const harvested = harvest(lang);
  const releases = {};
  const fallbacks = [];
  for (const version of versions) {
    const translated = harvested.get(version);
    if (translated && translated.length === enReleases[version].length) {
      releases[version] = translated;
    } else {
      releases[version] = enReleases[version];
      fallbacks.push(version);
    }
  }
  fallbackTotal += fallbacks.length;

  const target = join(LOCALES_DIR, file);
  const data = JSON.parse(readFileSync(target, "utf8"));
  data.whatsNewDialog.releases = releases;
  data.whatsNewDialog.releaseStamps = enStamps;
  if (!DRY_RUN) writeFileSync(target, `${JSON.stringify(data, null, 2)}\n`, "utf8");

  const note = fallbacks.length
    ? `, ${fallbacks.length} left in English: ${fallbacks.join(", ")}`
    : "";
  console.log(`${lang}: ${versions.length - fallbacks.length}/${versions.length} recovered${note}`);
}

console.log(
  DRY_RUN
    ? `[backfill-whatsnew] dry run, nothing written (${fallbackTotal} English fallbacks)`
    : `[backfill-whatsnew] wrote ${files.length} locale files (${fallbackTotal} English fallbacks)`,
);
