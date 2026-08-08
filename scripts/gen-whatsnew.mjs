#!/usr/bin/env node
/**
 * gen-whatsnew.mjs
 *
 * Writes src/locales/en.json's `whatsNewDialog.highlights` (a string array) from
 * the "### Highlights" block of the top (latest) section of CHANGELOG.md, so the
 * in-app "What's New" modal shows a few short release notes instead of truncated
 * changelog prose. It also writes `whatsNewDialog.highlightsStamp`.
 *
 * Alongside those it writes `whatsNewDialog.releases`, the same bullets for EVERY
 * CHANGELOG section that carries a "### Highlights" block, keyed by version, and
 * `whatsNewDialog.releaseStamps`, one digest per version. Someone who skips three
 * releases and updates once should read what changed across all three, so the
 * modal needs the archive rather than only the release it happens to land on.
 * `highlights` stays as the newest entry of that archive: it is what a locale
 * check, a test and the modal fallback already read, and duplicating one array is
 * cheaper than moving four gates at once.
 *
 * The archive is generated from CHANGELOG.md in full rather than accumulated in
 * en.json, so the changelog stays the single source and a past section that gets
 * reworded moves its own digest instead of going unnoticed. Sections predating
 * the "### Highlights" convention have no entry and are simply absent from the
 * modal, which is correct: there is nothing written to show for them.
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
function digestOf(items) {
  return createHash("sha256").update(JSON.stringify(items)).digest("hex").slice(0, 8);
}

function stampFor(version, items) {
  return `${version}+${digestOf(items)}`;
}

const AUTHORING_HELP =
  "Add a '### Highlights' block to the latest CHANGELOG.md section (after the intro paragraph, " +
  "before '### Added') with at most 5 plain-sentence bullets, each at most 140 characters, " +
  "no backticks and no 'vX.Y.Z:' prefix.";

/**
 * Split CHANGELOG.md into its "## " sections, newest first. A section keeps the
 * version its heading declares ("## v0.16.9 (...)" gives "0.16.9"); a heading
 * that declares no version keeps null and is skipped by the archive, since a
 * bullet nobody can date has nothing to be shown after.
 */
function splitSections(lines) {
  const sections = [];
  let current = null;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      const m = line.match(/^##\s+v([0-9][0-9.]*[0-9]|[0-9])/);
      current = { version: m ? m[1] : null, lines: [line] };
      sections.push(current);
      continue;
    }
    if (current) current.lines.push(line);
  }
  return sections;
}

/**
 * The bullets of one section's "### Highlights" block, or null when it has none.
 *
 * A bullet may be wrapped over several lines. The continuation lines are joined
 * back on with a single space instead of reading the first physical line and
 * dropping the rest, which would truncate the note without saying so.
 */
function highlightsOf(section) {
  const head = section.lines.findIndex((l) => /^###\s+Highlights\s*$/i.test(l));
  if (head < 0) return null;

  const items = [];
  let current = null;
  const flush = () => {
    if (current !== null) items.push(current.trim());
    current = null;
  };
  for (let i = head + 1; i < section.lines.length; i++) {
    const line = section.lines[i];
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
  return items;
}

/** The authoring rules, as a list of complaints (empty when the bullets pass). */
function authoringProblems(items) {
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
  return problems;
}

function build() {
  const version = JSON.parse(readFileSync(PKG, "utf-8")).version;
  const lines = readFileSync(CHANGELOG, "utf-8").split("\n");

  const sections = splitSections(lines);
  if (sections.length === 0) {
    throw new Error("[gen-whatsnew] No '## ' section found in CHANGELOG.md");
  }
  const latest = sections[0];

  // Freshness guard: the latest section must reference the current version.
  if (!latest.lines.join("\n").includes(`v${version}`)) {
    throw new StaleChangelogError(
      `[gen-whatsnew] CHANGELOG.md's latest section does not mention current version v${version}. ` +
        "Add a CHANGELOG entry for this release before building.",
    );
  }

  const items = highlightsOf(latest);
  if (items === null) {
    throw new StaleChangelogError(
      `[gen-whatsnew] CHANGELOG.md's latest section (v${version}) has no '### Highlights' block. ` +
        AUTHORING_HELP,
    );
  }
  if (items.length === 0) {
    throw new StaleChangelogError(
      `[gen-whatsnew] CHANGELOG.md's '### Highlights' block for v${version} has no bullets. ` +
        AUTHORING_HELP,
    );
  }

  // Every section with a Highlights block, newest first, so that an operator who
  // skipped several releases reads all of them at once. The rules are applied to
  // the archived sections too: a past bullet is shown verbatim in the modal
  // exactly like the current one, so nothing here may rely on being trimmed.
  const releases = {};
  const releaseStamps = {};
  const problems = [];
  for (const section of sections) {
    if (!section.version) continue;
    const bullets = section.version === latest.version ? items : highlightsOf(section);
    if (bullets === null || bullets.length === 0) continue;
    if (releases[section.version]) {
      problems.push(
        `v${section.version} has more than one CHANGELOG section carrying '### Highlights'`,
      );
      continue;
    }
    for (const p of authoringProblems(bullets)) {
      problems.push(`v${section.version}: ${p}`);
    }
    releases[section.version] = bullets;
    releaseStamps[section.version] = digestOf(bullets);
  }

  if (problems.length > 0) {
    throw new Error(
      "[gen-whatsnew] '### Highlights' bullets break the authoring rules:\n" +
        problems.map((p) => `  - ${p}`).join("\n") +
        `\n${AUTHORING_HELP} Rewrite the bullets; they are shown verbatim and are never truncated.`,
    );
  }

  return { version, items, releases, releaseStamps };
}

function readLocale() {
  return JSON.parse(readFileSync(OUT, "utf-8"));
}

function main() {
  const { version, items, releases, releaseStamps } = build();
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
    // The archive is compared as a whole, key order included: the modal renders
    // the versions in the order they appear, so a reordered object is a visible
    // difference and not a formatting one.
    if (JSON.stringify(dialog?.releases) !== JSON.stringify(releases)) {
      drift.push(
        `whatsNewDialog.releases does not match the per-version '### Highlights' blocks of ` +
          `CHANGELOG.md (${Object.keys(releases).length} versions carry one)`,
      );
    }
    if (JSON.stringify(dialog?.releaseStamps) !== JSON.stringify(releaseStamps)) {
      drift.push(
        "whatsNewDialog.releaseStamps does not match the digests of whatsNewDialog.releases",
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
  dialog.releases = releases;
  dialog.releaseStamps = releaseStamps;
  writeFileSync(OUT, `${JSON.stringify(locale, null, 2)}\n`, "utf-8");
  console.log(
    `[gen-whatsnew] wrote ${items.length} highlights (${stamp}) and an archive of ` +
      `${Object.keys(releases).length} releases to ${OUT}`,
  );
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
