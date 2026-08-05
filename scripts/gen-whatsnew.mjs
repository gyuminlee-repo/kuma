#!/usr/bin/env node
/**
 * gen-whatsnew.mjs
 *
 * Writes src/locales/en.json's `whatsNewDialog.highlights` (a string array) from
 * the "### Highlights" block of the top (latest) section of CHANGELOG.md, so the
 * in-app "What's New" modal shows a few short release notes instead of truncated
 * changelog prose. It also writes `whatsNewDialog.highlightsStamp`.
 *
 * The stamp is "<version>+<digest8>": the package.json version those bullets were
 * generated from, then the first 8 hex characters of the sha256 of
 * JSON.stringify(highlights). The array order is part of the digest and is never
 * sorted, because the bullets are shown in the order they were written.
 *
 * The digest half is what makes the stamp mean "this exact English wording",
 * not merely "some wording from this release". A version-only stamp moves at a
 * release boundary and nowhere else, so rewording a bullet inside one version
 * (which this branch did twice to the v0.15.6 bullets) left all nine
 * translations describing the old wording with every gate green.
 *
 * The nine other locales translate the array by hand and copy that same stamp.
 * The stamp exists because nothing else can see a stale translation: --check
 * below only ever compares en.json against the CHANGELOG, and
 * scripts/i18n-parity.mjs compares flattened key sets, where an array shows up
 * as `highlights.0`, `highlights.1` ... so only a differing element count or an
 * empty string is visible there. A locale still carrying last release's wording
 * has the same key count and the same non-empty values, so without the stamp
 * every gate stays green while that locale shows the previous release's notes.
 * scripts/i18n-parity.mjs therefore fails when a locale's `highlightsStamp`
 * does not match en.json's.
 *
 * Authoring rules enforced here (the point is to force short notes, so a bullet
 * that breaks a rule fails the build instead of being trimmed):
 *   - at most 5 bullets, each at most 140 characters
 *   - no backticks / code identifiers, no "vX.Y.Z:" prefix
 *
 * A bullet wrapped over several lines in CHANGELOG.md is joined back into one
 * string (single space between lines) before those rules are applied. Reading
 * only the physical "- " line would drop the rest of a wrapped bullet without
 * saying so, and a silently truncated note is the failure this generator exists
 * to prevent. A bullet ends at a blank line, the next "- ", or a "###" heading.
 *
 * Freshness guard: the latest CHANGELOG section MUST reference the current
 * package.json version (e.g. `v0.15.6`) and MUST carry a "### Highlights" block;
 * otherwise generation/--check fails so a release cannot ship a stale modal.
 * Both of those "the CHANGELOG is not ready for this release yet" cases exit with
 * EXIT_STALE_CHANGELOG (2) instead of the generic EXIT_ERROR (1) so callers (see
 * scripts/sync-version.sh) can tell them apart from "generation broke for some
 * other reason" without string-matching the error message. Rule violations above
 * are authoring mistakes, not staleness, and exit with EXIT_ERROR (1).
 *
 * Usage:
 *   node scripts/gen-whatsnew.mjs           # write highlights + stamp into en.json
 *   node scripts/gen-whatsnew.mjs --check   # verify en.json without writing (CI/sync)
 *
 * Exit codes, in both modes:
 *   0  en.json was written, or (--check) its highlights match the CHANGELOG block
 *      and its highlightsStamp matches the version and those bullets
 *   1  (--check) en.json is stale: wrong bullets or wrong stamp. Also any other
 *      generator failure, including bullets that break the authoring rules above
 *   2  CHANGELOG.md is not ready for this release (EXIT_STALE_CHANGELOG): its
 *      latest section does not mention the current version, or has no
 *      "### Highlights" block, or that block has no bullets. Split out from 1 so
 *      scripts/sync-version.sh can warn and continue instead of failing the hook
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CHANGELOG = resolve(ROOT, "CHANGELOG.md");
const PKG = resolve(ROOT, "package.json");
const OUT = resolve(ROOT, "src/locales/en.json");

const MAX_ITEMS = 5;
const MAX_LENGTH = 140;

const EXIT_ERROR = 1;
const EXIT_STALE_CHANGELOG = 2;

class StaleChangelogError extends Error {}

/**
 * The value written to (and checked against) whatsNewDialog.highlightsStamp:
 * "<version>+<digest8>". The digest covers the English bullets verbatim and in
 * order, so any edit to the wording, however small, moves the stamp and leaves
 * the nine hand-translated locales visibly behind it.
 */
function stampFor(version, items) {
  const digest8 = createHash("sha256")
    .update(JSON.stringify(items))
    .digest("hex")
    .slice(0, 8);
  return `${version}+${digest8}`;
}

const AUTHORING_HELP =
  "Add a '### Highlights' block to the latest CHANGELOG.md section (after the intro paragraph, " +
  "before '### Added') with at most 5 plain-sentence bullets, each at most 140 characters, " +
  "no backticks and no 'vX.Y.Z:' prefix.";

function build() {
  const version = JSON.parse(readFileSync(PKG, "utf-8")).version;
  const lines = readFileSync(CHANGELOG, "utf-8").split("\n");

  const start = lines.findIndex((l) => l.startsWith("## "));
  if (start < 0) throw new Error("[gen-whatsnew] No '## ' section found in CHANGELOG.md");
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (lines[i].startsWith("## ")) {
      end = i;
      break;
    }
  }
  const section = lines.slice(start, end);

  // Freshness guard: the latest section must reference the current version.
  if (!section.join("\n").includes(`v${version}`)) {
    throw new StaleChangelogError(
      `[gen-whatsnew] CHANGELOG.md's latest section does not mention current version v${version}. ` +
        "Add a CHANGELOG entry for this release before building.",
    );
  }

  const head = section.findIndex((l) => /^###\s+Highlights\s*$/i.test(l));
  if (head < 0) {
    throw new StaleChangelogError(
      `[gen-whatsnew] CHANGELOG.md's latest section (v${version}) has no '### Highlights' block. ` +
        AUTHORING_HELP,
    );
  }

  // A bullet may be wrapped over several lines. Join the continuation lines
  // back on with a single space instead of reading the first physical line and
  // dropping the rest, which would truncate the note without saying so.
  const items = [];
  let current = null;
  const flush = () => {
    if (current !== null) items.push(current.trim());
    current = null;
  };
  for (let i = head + 1; i < section.length; i++) {
    const line = section[i];
    if (line.startsWith("###")) break;
    const b = line.match(/^-\s+(.+)$/);
    if (b) {
      flush();
      current = b[1].trim();
      continue;
    }
    if (line.trim() === "") {
      flush();
      continue;
    }
    if (current !== null) current = `${current} ${line.trim()}`;
  }
  flush();

  if (items.length === 0) {
    throw new StaleChangelogError(
      `[gen-whatsnew] CHANGELOG.md's '### Highlights' block for v${version} has no bullets. ` +
        AUTHORING_HELP,
    );
  }

  const problems = [];
  if (items.length > MAX_ITEMS) {
    problems.push(`${items.length} bullets, at most ${MAX_ITEMS} allowed`);
  }
  for (const text of items) {
    if (text.length > MAX_LENGTH) {
      problems.push(`${text.length} chars (max ${MAX_LENGTH}): ${text}`);
    }
    if (text.includes("`")) {
      problems.push(`backtick / code identifier not allowed: ${text}`);
    }
    if (/^v\d[\w.]*:/.test(text)) {
      problems.push(`'vX.Y.Z:' prefix not allowed: ${text}`);
    }
  }
  if (problems.length > 0) {
    throw new Error(
      `[gen-whatsnew] '### Highlights' bullets for v${version} break the authoring rules:\n` +
        problems.map((p) => `  - ${p}`).join("\n") +
        `\n${AUTHORING_HELP} Rewrite the bullets; they are shown verbatim and are never truncated.`,
    );
  }

  return { version, items };
}

function readLocale() {
  return JSON.parse(readFileSync(OUT, "utf-8"));
}

function main() {
  const { version, items } = build();
  const stamp = stampFor(version, items);
  const locale = readLocale();
  const dialog = locale.whatsNewDialog;

  if (process.argv.includes("--check")) {
    const drift = [];
    if (JSON.stringify(dialog?.highlights) !== JSON.stringify(items)) {
      drift.push(
        "whatsNewDialog.highlights does not match CHANGELOG.md's '### Highlights' block",
      );
    }
    if (dialog?.highlightsStamp !== stamp) {
      drift.push(
        `whatsNewDialog.highlightsStamp is ${JSON.stringify(dialog?.highlightsStamp)}, ` +
          `expected "${stamp}" (package.json version + sha256 of these bullets)`,
      );
    }
    if (drift.length > 0) {
      console.error(
        "[gen-whatsnew] drift in src/locales/en.json:\n" +
          drift.map((d) => `  - ${d}`).join("\n") +
          "\nRun `pnpm gen:whatsnew`. Then re-translate the highlights arrays in the other " +
          "src/locales/*.json and set each of their highlightsStamp to the same value, " +
          "or `node scripts/i18n-parity.mjs` fails.",
      );
      process.exit(EXIT_ERROR);
    }
    console.log(`[gen-whatsnew] up to date (${stamp}, ${items.length} highlights)`);
    return;
  }

  if (!dialog) {
    throw new Error("[gen-whatsnew] src/locales/en.json has no 'whatsNewDialog' block.");
  }
  dialog.highlights = items;
  dialog.highlightsStamp = stamp;
  writeFileSync(OUT, `${JSON.stringify(locale, null, 2)}\n`, "utf-8");
  console.log(`[gen-whatsnew] wrote ${items.length} highlights (${stamp}) to ${OUT}`);
}

try {
  main();
} catch (err) {
  if (err instanceof StaleChangelogError) {
    console.error(err.message);
    process.exit(EXIT_STALE_CHANGELOG);
  }
  console.error(err instanceof Error ? (err.stack ?? err.message) : String(err));
  process.exit(EXIT_ERROR);
}
