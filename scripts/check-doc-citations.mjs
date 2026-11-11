#!/usr/bin/env node
/**
 * check-doc-citations.mjs
 *
 * Answers one question for every tracked source and documentation file:
 * when the file cites a markdown document, does that path actually resolve
 * inside this repository?
 *
 * Plenty of citations here do not resolve, for reasons that are structural
 * rather than accidental: some documents are generated at build time and are
 * gitignored, some live in internal directories that a public repository will
 * never carry, some belong to a sibling repository, and some are simply gone.
 * A reader following such a citation finds nothing and cannot tell which case
 * they hit. This checker does not clean those up. It freezes them into an
 * explicit ledger (scripts/doc-citations-allow.json, one reason per entry) and
 * fails the build when a citation that nobody has accounted for appears.
 *
 * The same file carries a second, independent check with the same shape: a
 * ratchet on line-number citations. A comment that names a position in another
 * file goes stale the moment that file gains or loses a line above the cited
 * one, and nothing announces it. Of the citations present when this ratchet was
 * added, only thirteen sat next to a backticked symbol that a machine could
 * compare, and ten of those thirteen were already pointing at the wrong line.
 * Verifying the rest is not possible: a line number alone carries no claim to
 * check. So this does not verify them and does not rewrite them either. It
 * freezes the set that exists (scripts/line-citations-ledger.json) and fails
 * when a citation nobody has accounted for appears. Existing ones move to
 * symbol names opportunistically, whenever their file is open for other work.
 *
 * Usage:
 *   node scripts/check-doc-citations.mjs            check, exit 1 on a new unresolved citation
 *   node scripts/check-doc-citations.mjs --list     report every unresolved citation, never fails
 *   node scripts/check-doc-citations.mjs --selftest run the labelled corpus, exit 1 on a mismatch
 *   node scripts/check-doc-citations.mjs --write-line-ledger
 *                                                   regenerate the line-citation ledger from the
 *                                                   working tree, accepting whatever it now holds
 *
 * Exit codes: 0 clean, 1 check or selftest failed, 2 the checker itself could not run.
 *
 * Node standard library only, matching the rest of scripts/.
 */

import { spawnSync } from "node:child_process";
import { readFileSync, existsSync, writeFileSync } from "node:fs";
import { dirname, resolve, posix as posixPath } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ALLOWLIST_FILE = "scripts/doc-citations-allow.json";
const CORPUS_FILE = "scripts/check-doc-citations.corpus.json";
const LINE_LEDGER_FILE = "scripts/line-citations-ledger.json";

/** Files whose text is searched for citations. */
const SCANNED_EXTENSIONS = [
  ".py",
  ".ts",
  ".tsx",
  ".rs",
  ".mjs",
  ".json",
  ".md",
  ".toml",
  ".yml",
  ".yaml",
];

/**
 * The checker's own ledger and its fixture are skipped. Both exist only to
 * record citations that are known not to resolve, so scanning them would make
 * the checker report its own bookkeeping.
 */
const SELF_EXCLUDED = new Set([ALLOWLIST_FILE, CORPUS_FILE, LINE_LEDGER_FILE]);

/**
 * mkdocs resolves nav and exclude entries against docs_dir, so those roots are tried too.
 * The user guide takes its page bodies from docs/help/<lang> through
 * docs/site/help_pages.py, so a nav entry such as kuro-index.md names a file
 * there. Both language folders hold the same file names.
 */
const DOCS_ROOTS = ["docs", "docs/help/en"];

/**
 * Kept in step with the category list documented in the allowlist header.
 * A category disappears from this list once nothing is filed under it: the
 * "stale" category existed while four citations pointed at pages that had
 * moved, and went away when those citations were corrected.
 */
const CATEGORIES = ["generated", "internal", "lost", "external", "prose"];

/**
 * Absolute URLs are removed before matching. Without this, the tail of
 * https://host/path/DOC.md reads as a repository path. Stops at the closing
 * delimiters that markdown links, quotes and parentheses put after a URL.
 */
const URL_PATTERN = /[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^\s)\]}>"'`]+/g;

/**
 * A markdown reference: optional slash-separated segments then a filename.
 * A leading segment may be "." or "..", which is why "." is inside the class.
 * The trailing boundary keeps ".mdx" and similar out. No slash is required,
 * because real lost citations here are written as a bare filename.
 */
const CITATION_PATTERN = /((?:[\w.-]+\/)*[\w.-]+\.md)\b/g;

/**
 * Files whose text is searched for line-number citations. Markdown is left out
 * on purpose: the audit notes under docs/ record a position as it stood on the
 * day they were written and are meant to go stale, so freezing them would fill
 * the ledger with entries that carry no obligation.
 */
const LINE_SCANNED_EXTENSIONS = [".py", ".ts", ".tsx", ".rs", ".mjs"];

/**
 * A position in another file: a path ending in one of the project source or
 * config extensions, a colon, then a single line, a range, or a comma list of
 * either. The cited extension set is wider than the scanned one because a
 * comment can name a line inside a workbook of generated types, a workflow or
 * an audit note just as easily as one inside code.
 */
const LINE_CITATION_PATTERN =
  /((?:[\w.-]+\/)*[\w.-]+\.(?:py|ts|tsx|rs|mjs|json|md|toml|yml|yaml)):(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)/g;

/**
 * How a frozen line citation came to be allowed. The first three are decided by
 * the scan, the last three by hand in the ledger, where a regeneration keeps
 * them.
 *
 *   frozen        the cited path resolves to exactly one tracked file.
 *   ambiguous     two or more tracked files carry that name, so a reader cannot
 *                 tell which one the line number belongs to.
 *   unresolved    nothing tracked carries that name, and nobody has said why.
 *   external      the path belongs to a sibling repository, outside this one.
 *   stdlib        the path belongs to a language standard library.
 *   test-literal  the string is a fixture or an expected message, not a citation.
 */
const LINE_CATEGORIES = [
  "frozen",
  "ambiguous",
  "unresolved",
  "external",
  "stdlib",
  "test-literal",
];

/** Categories the scan assigns on its own; the rest survive a regeneration. */
const LINE_MECHANICAL_CATEGORIES = new Set(["frozen", "ambiguous", "unresolved"]);

// --------------------------------------------------------------------------
// extraction
// --------------------------------------------------------------------------

/** @returns {string[]} references cited on one line, in order of appearance. */
export function extractFromLine(line) {
  const scrubbed = line.replace(URL_PATTERN, " ");
  const found = [];
  for (const match of scrubbed.matchAll(CITATION_PATTERN)) {
    found.push(match[1]);
  }
  return found;
}

/** @returns {{ref: string, line: number}[]} */
function extractFromContent(content) {
  const out = [];
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    for (const ref of extractFromLine(lines[i])) {
      out.push({ ref, line: i + 1 });
    }
  }
  return out;
}

/** @returns {string[]} line citations on one line, each as "path:lines". */
export function extractLineCitationsFromLine(line) {
  const scrubbed = line.replace(URL_PATTERN, " ");
  const found = [];
  for (const match of scrubbed.matchAll(LINE_CITATION_PATTERN)) {
    found.push(`${match[1]}:${match[2]}`);
  }
  return found;
}

/**
 * Build the lookup a classification needs: every tracked path, and every
 * tracked path grouped by its final segment.
 *
 * @param {string[]} tracked
 */
export function buildTrackedIndex(tracked) {
  const byBasename = new Map();
  for (const path of tracked) {
    const base = path.slice(path.lastIndexOf("/") + 1);
    if (!byBasename.has(base)) byBasename.set(base, []);
    byBasename.get(base).push(path);
  }
  return { set: new Set(tracked), byBasename };
}

/**
 * Decide whether a reader could tell which file a cited path names. The line
 * number itself is never checked: see the header for why that is not possible
 * here.
 *
 * @returns {"frozen"|"ambiguous"|"unresolved"}
 */
export function classifyLineCitation(citedPath, index) {
  if (index.set.has(citedPath)) return "frozen";

  const base = citedPath.slice(citedPath.lastIndexOf("/") + 1);
  const sameName = index.byBasename.get(base) ?? [];
  const suffixMatches = sameName.filter((t) => t === citedPath || t.endsWith(`/${citedPath}`));
  if (suffixMatches.length === 1) return "frozen";
  if (suffixMatches.length > 1) return "ambiguous";
  if (sameName.length === 1) return "frozen";
  if (sameName.length > 1) return "ambiguous";
  return "unresolved";
}

// --------------------------------------------------------------------------
// resolution
// --------------------------------------------------------------------------

/** Normalise a repo-relative path, rejecting anything that climbs above the root. */
function insideRoot(candidate) {
  const normalised = posixPath.normalize(candidate);
  if (normalised === ".." || normalised.startsWith("../")) return null;
  return normalised;
}

/**
 * @returns {"exact"|"relative"|"docs"|null} the rule that accepted the
 * reference, or null when nothing in the repository matches it.
 */
export function resolveReference(ref, sourcePath, trackedSet) {
  if (trackedSet.has(ref)) return "exact";

  const fromSibling = insideRoot(posixPath.join(posixPath.dirname(sourcePath), ref));
  if (fromSibling && trackedSet.has(fromSibling)) return "relative";

  for (const root of DOCS_ROOTS) {
    const fromDocs = insideRoot(posixPath.join(root, ref));
    if (fromDocs && trackedSet.has(fromDocs)) return "docs";
  }

  return null;
}

// --------------------------------------------------------------------------
// inputs
// --------------------------------------------------------------------------

function fail(message) {
  console.error(`[check-doc-citations] ${message}`);
  process.exit(2);
}

function listTrackedFiles() {
  const result = spawnSync("git", ["ls-files", "-z"], {
    cwd: ROOT,
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) fail(`could not run git: ${result.error.message}`);
  if (result.status !== 0) fail(`git ls-files exited ${result.status}`);
  return result.stdout.split("\0").filter(Boolean);
}

function hasScannedExtension(path) {
  return SCANNED_EXTENSIONS.some((ext) => path.endsWith(ext));
}

function loadAllowlist() {
  const file = resolve(ROOT, ALLOWLIST_FILE);
  if (!existsSync(file)) {
    return { byPath: new Map(), missing: true };
  }
  let parsed;
  try {
    parsed = JSON.parse(readFileSync(file, "utf-8"));
  } catch (err) {
    fail(`${ALLOWLIST_FILE} is not valid JSON: ${err.message}`);
  }
  if (!Array.isArray(parsed.allow)) {
    fail(`${ALLOWLIST_FILE} must contain an "allow" array`);
  }
  const byPath = new Map();
  for (const entry of parsed.allow) {
    if (!entry || typeof entry.path !== "string" || entry.path.length === 0) {
      fail(`${ALLOWLIST_FILE}: every entry needs a non-empty "path"`);
    }
    if (typeof entry.reason !== "string" || entry.reason.trim().length === 0) {
      fail(`${ALLOWLIST_FILE}: entry "${entry.path}" needs a non-empty "reason"`);
    }
    if (!CATEGORIES.includes(entry.category)) {
      fail(
        `${ALLOWLIST_FILE}: entry "${entry.path}" has category "${entry.category}", ` +
          `expected one of ${CATEGORIES.join(", ")}`
      );
    }
    if (byPath.has(entry.path)) {
      fail(`${ALLOWLIST_FILE}: duplicate entry for "${entry.path}"`);
    }
    byPath.set(entry.path, entry);
  }
  return { byPath, missing: false };
}

// --------------------------------------------------------------------------
// scan
// --------------------------------------------------------------------------

function scan() {
  const tracked = listTrackedFiles();
  const trackedSet = new Set(tracked);
  const targets = tracked.filter((p) => hasScannedExtension(p) && !SELF_EXCLUDED.has(p));

  let occurrences = 0;
  /** @type {Map<string, {source: string, line: number}[]>} */
  const unresolved = new Map();

  for (const path of targets) {
    let content;
    try {
      content = readFileSync(resolve(ROOT, path), "utf-8");
    } catch {
      continue; // deleted from the working tree but still in the index
    }
    for (const { ref, line } of extractFromContent(content)) {
      occurrences += 1;
      if (resolveReference(ref, path, trackedSet) !== null) continue;
      if (!unresolved.has(ref)) unresolved.set(ref, []);
      unresolved.get(ref).push({ source: path, line });
    }
  }

  return { scanned: targets.length, occurrences, unresolved };
}

/** The ledger key for one citation site: which file cites what. */
export function lineCitationKey(source, cite) {
  return `${source}\t${cite}`;
}

/**
 * Keyed by citing file and cited string rather than by either alone. The cited
 * string on its own would let a second file re-cite a frozen position and pass
 * unnoticed. The line the comment sits on would move every time anything above
 * it changes, so the ledger would churn against edits that cite nothing.
 */
function scanLineCitations() {
  const tracked = listTrackedFiles();
  const index = buildTrackedIndex(tracked);
  const targets = tracked.filter(
    (p) => LINE_SCANNED_EXTENSIONS.some((ext) => p.endsWith(ext)) && !SELF_EXCLUDED.has(p)
  );

  let occurrences = 0;
  /** @type {Map<string, {source: string, cite: string, category: string, lines: number[]}>} */
  const sites = new Map();

  for (const path of targets) {
    let content;
    try {
      content = readFileSync(resolve(ROOT, path), "utf-8");
    } catch {
      continue;
    }
    const lines = content.split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      for (const cite of extractLineCitationsFromLine(lines[i])) {
        occurrences += 1;
        const key = lineCitationKey(path, cite);
        const existing = sites.get(key);
        if (existing) {
          existing.lines.push(i + 1);
          continue;
        }
        sites.set(key, {
          source: path,
          cite,
          category: classifyLineCitation(cite.slice(0, cite.lastIndexOf(":")), index),
          lines: [i + 1],
        });
      }
    }
  }

  return { scanned: targets.length, occurrences, sites };
}

function loadLineLedger() {
  const file = resolve(ROOT, LINE_LEDGER_FILE);
  if (!existsSync(file)) {
    return { byKey: new Map(), missing: true };
  }
  let parsed;
  try {
    parsed = JSON.parse(readFileSync(file, "utf-8"));
  } catch (err) {
    fail(`${LINE_LEDGER_FILE} is not valid JSON: ${err.message}`);
  }
  if (!Array.isArray(parsed.frozen)) {
    fail(`${LINE_LEDGER_FILE} must contain a "frozen" array`);
  }
  const byKey = new Map();
  for (const entry of parsed.frozen) {
    for (const field of ["source", "cite", "reason"]) {
      if (!entry || typeof entry[field] !== "string" || entry[field].trim().length === 0) {
        fail(`${LINE_LEDGER_FILE}: every entry needs a non-empty "${field}"`);
      }
    }
    if (!LINE_CATEGORIES.includes(entry.category)) {
      fail(
        `${LINE_LEDGER_FILE}: entry "${entry.source} -> ${entry.cite}" has category ` +
          `"${entry.category}", expected one of ${LINE_CATEGORIES.join(", ")}`
      );
    }
    const key = lineCitationKey(entry.source, entry.cite);
    if (byKey.has(key)) {
      fail(`${LINE_LEDGER_FILE}: duplicate entry for "${entry.source} -> ${entry.cite}"`);
    }
    byKey.set(key, entry);
  }
  return { byKey, missing: false };
}

/** Sort entries so a regeneration of the same tree writes the same bytes. */
function sortLedgerEntries(entries) {
  return [...entries].sort(
    (a, b) => a.source.localeCompare(b.source) || a.cite.localeCompare(b.cite)
  );
}

const MECHANICAL_REASONS = {
  frozen:
    "Frozen when the line-citation ratchet was added; the cited file resolves, the line number is unverifiable. Replace with a symbol name when this file is next edited.",
  ambiguous:
    "Frozen when the line-citation ratchet was added; two or more tracked files carry this name, so the citation does not say which one. Replace with a symbol name when this file is next edited.",
  unresolved:
    "Frozen when the line-citation ratchet was added; nothing tracked carries this path. Give it a category and a reason, or replace the citation.",
};

/**
 * Rebuild the ledger from the working tree. Hand-written categories and reasons
 * survive for a key that is still cited, because the scan cannot tell a sibling
 * repository or a test fixture from a citation on its own.
 */
function runWriteLineLedger() {
  const { sites } = scanLineCitations();
  const { byKey } = loadLineLedger();

  const entries = [];
  const added = [];
  for (const [key, site] of sites) {
    const previous = byKey.get(key);
    if (previous && !LINE_MECHANICAL_CATEGORIES.has(previous.category)) {
      entries.push({
        source: site.source,
        cite: site.cite,
        category: previous.category,
        reason: previous.reason,
      });
      continue;
    }
    if (!previous) added.push(site);
    entries.push({
      source: site.source,
      cite: site.cite,
      category: site.category,
      reason: previous ? previous.reason : MECHANICAL_REASONS[site.category],
    });
  }

  const dropped = [...byKey.keys()].filter((key) => !sites.has(key)).sort();
  const header = existsSync(resolve(ROOT, LINE_LEDGER_FILE))
    ? JSON.parse(readFileSync(resolve(ROOT, LINE_LEDGER_FILE), "utf-8"))._comment
    : LEDGER_HEADER;

  const payload = { _comment: header, frozen: sortLedgerEntries(entries) };
  writeFileSync(resolve(ROOT, LINE_LEDGER_FILE), `${JSON.stringify(payload, null, 2)}\n`, "utf-8");

  console.log(
    `[check-doc-citations] wrote ${LINE_LEDGER_FILE}: ${entries.length} entries, ` +
      `${added.length} added, ${dropped.length} dropped`
  );
  for (const site of sortLedgerEntries(added)) {
    console.log(`  + ${site.source} -> ${site.cite} (${site.category})`);
  }
  for (const key of dropped) {
    console.log(`  - ${key.replace("\t", " -> ")}`);
  }
  console.log("");
  console.log("  Running this accepts every citation above as permanent debt. Say in the pull");
  console.log("  request why a new line-number citation was preferred to a symbol name.");
}

const LEDGER_HEADER = [
  "Ledger of line-number citations in source files, frozen so that no new one arrives unnoticed.",
  "Written and rechecked by scripts/check-doc-citations.mjs; regenerate with --write-line-ledger.",
  "",
  "A key is the citing file plus the cited string. Neither half alone works: the cited string on",
  "its own would let a second file re-cite a frozen position and pass, and the line the comment",
  "sits on would move whenever anything above it changed.",
  "",
  "Nothing here is verified. The line number is checked against nothing, because a bare position",
  "carries no claim a machine can test. What this buys is the ratchet: an unlisted citation fails",
  "the check, so the count only goes down. Existing entries are corrected opportunistically, when",
  "their file is open for other work, and the entry then disappears on the next regeneration.",
];

// --------------------------------------------------------------------------
// allowlist upkeep
// --------------------------------------------------------------------------

/**
 * An allowlist entry earns its place only while some citation still needs it.
 * Once the last citation to a path is corrected or deleted, the entry stops
 * describing anything and the ledger starts to drift away from the repository.
 * A ledger that only ever grows is a rubber stamp, so a stranded entry is a
 * failure rather than a note.
 *
 * @param {string[]} allowPaths paths listed in the allowlist
 * @param {Iterable<string>} unresolvedRefs references the scan could not resolve
 * @returns {string[]} allowlist paths that no unresolved citation points at
 */
export function findUnusedAllowEntries(allowPaths, unresolvedRefs) {
  const stillCited = new Set(unresolvedRefs);
  return allowPaths.filter((path) => !stillCited.has(path)).sort((a, b) => a.localeCompare(b));
}

// --------------------------------------------------------------------------
// commands
// --------------------------------------------------------------------------

function sortedRefs(unresolved) {
  return [...unresolved.keys()].sort((a, b) => a.localeCompare(b));
}

function reportUnusedEntries(unused, byPath, log) {
  const noun = unused.length === 1 ? "entry" : "entries";
  const verb = unused.length === 1 ? "describes" : "describe";
  log(
    `[check-doc-citations] FAIL: ${unused.length} allowlist ${noun} no longer ` +
      `${verb} any citation in the repository`
  );
  for (const path of unused) {
    log(`  ${path}`);
    log(`    category: ${byPath.get(path).category}`);
    log(`    reason on file: ${byPath.get(path).reason}`);
  }
  log("");
  log("  Nothing cites these any more, so the recorded reason is no longer being checked");
  log("  against anything. Either drop the entry, or, if the citation is expected back,");
  log(`  update its reason in ${ALLOWLIST_FILE} to say why it is being held open.`);
}

function runCheck() {
  const { scanned, occurrences, unresolved } = scan();
  const { byPath, missing } = loadAllowlist();
  if (missing) {
    console.warn(`[check-doc-citations] ${ALLOWLIST_FILE} not found, treating the allowlist as empty`);
  }

  const offenders = sortedRefs(unresolved).filter((ref) => !byPath.has(ref));
  const allowedRefs = unresolved.size - offenders.length;
  const unused = findUnusedAllowEntries([...byPath.keys()], unresolved.keys());

  if (offenders.length > 0) {
    console.error(
      `[check-doc-citations] FAIL: ${offenders.length} cited document(s) do not resolve ` +
        `and are not listed in ${ALLOWLIST_FILE}`
    );
    for (const ref of offenders) {
      console.error(`  ${ref}`);
      for (const { source, line } of unresolved.get(ref)) {
        console.error(`    ${source}:${line}`);
      }
    }
    console.error("");
    console.error("  Point the citation at a tracked path, or add an entry with a reason to");
    console.error(`  ${ALLOWLIST_FILE}. Run with --list to see how the existing ones are classified.`);
  }

  if (unused.length > 0) {
    if (offenders.length > 0) console.error("");
    reportUnusedEntries(unused, byPath, (line) => console.error(line));
  }

  const lineFailed = checkLineCitations(offenders.length > 0 || unused.length > 0);

  if (offenders.length > 0 || unused.length > 0 || lineFailed) process.exit(1);

  console.log(
    `[check-doc-citations] OK: ${scanned} files scanned, ${occurrences} citations, ` +
      `${allowedRefs} unresolved reference(s), all accounted for in ${ALLOWLIST_FILE}, ` +
      `and every allowlist entry still describes a live citation`
  );
}

/**
 * The ratchet. A citation site the ledger does not list fails, because the
 * ledger was frozen from the tree and anything outside it is therefore new. A
 * ledger entry nothing cites any more also fails, so that a citation corrected
 * on the way past leaves the ledger shorter instead of leaving a stale excuse.
 *
 * @param {boolean} precededByOtherOutput whether to print a separating blank line
 * @returns {boolean} true when the ratchet failed
 */
function checkLineCitations(precededByOtherOutput) {
  const { scanned, occurrences, sites } = scanLineCitations();
  const { byKey, missing } = loadLineLedger();
  if (missing) {
    console.warn(
      `[check-doc-citations] ${LINE_LEDGER_FILE} not found, treating the line ledger as empty`
    );
  }

  const newSites = sortLedgerEntries([...sites.values()].filter((site) => !byKey.has(
    lineCitationKey(site.source, site.cite)
  )));
  const stranded = findUnusedAllowEntries([...byKey.keys()], sites.keys());

  if (newSites.length === 0 && stranded.length === 0) {
    console.log(
      `[check-doc-citations] OK: ${scanned} source files scanned, ${occurrences} line-number ` +
        `citation(s) in ${sites.size} frozen site(s), no new one and none stranded`
    );
    return false;
  }

  if (precededByOtherOutput) console.error("");

  if (newSites.length > 0) {
    const noun = newSites.length === 1 ? "citation" : "citations";
    console.error(
      `[check-doc-citations] FAIL: ${newSites.length} line-number ${noun} not listed in ` +
        `${LINE_LEDGER_FILE}`
    );
    for (const site of newSites) {
      console.error(`  ${site.source}:${site.lines.join(",")} cites ${site.cite}`);
    }
    console.error("");
    console.error("  A line number goes stale the moment the cited file gains a line above it,");
    console.error("  and nothing announces it. Cite the symbol name instead, and if the cited");
    console.error("  file is already in a .cross-layer-sync.json group, put the symbol in that");
    console.error("  group's symbols[] so its existence is checked. If a line number is genuinely");
    console.error(`  needed, run --write-line-ledger and justify it in the pull request.`);
  }

  if (stranded.length > 0) {
    if (newSites.length > 0) console.error("");
    const noun = stranded.length === 1 ? "entry" : "entries";
    console.error(
      `[check-doc-citations] FAIL: ${stranded.length} line ledger ${noun} no longer cited`
    );
    for (const key of stranded) {
      console.error(`  ${key.replace("\t", " -> ")}`);
    }
    console.error("");
    console.error("  The citation was corrected or deleted, which is the outcome this ratchet is");
    console.error("  for. Run --write-line-ledger to drop the entry.");
  }

  return true;
}

function runList() {
  const { scanned, occurrences, unresolved } = scan();
  const { byPath } = loadAllowlist();

  const buckets = new Map(CATEGORIES.map((c) => [c, []]));
  buckets.set("unclassified", []);
  for (const ref of sortedRefs(unresolved)) {
    const entry = byPath.get(ref);
    buckets.get(entry ? entry.category : "unclassified").push(ref);
  }

  let totalOccurrences = 0;
  for (const list of unresolved.values()) totalOccurrences += list.length;

  console.log(
    `[check-doc-citations] ${scanned} files scanned, ${occurrences} citations, ` +
      `${unresolved.size} unresolved reference(s) in ${totalOccurrences} place(s)`
  );

  for (const [category, refs] of buckets) {
    if (refs.length === 0) continue;
    console.log("");
    console.log(`## ${category} (${refs.length})`);
    for (const ref of refs) {
      const entry = byPath.get(ref);
      console.log(`  ${ref}`);
      if (entry) console.log(`    reason: ${entry.reason}`);
      for (const { source, line } of unresolved.get(ref)) {
        console.log(`    cited at ${source}:${line}`);
      }
    }
  }

  const unused = findUnusedAllowEntries([...byPath.keys()], unresolved.keys());
  if (unused.length > 0) {
    console.log("");
    console.log(`## no longer cited (${unused.length})`);
    console.log("  These allowlist entries describe nothing in the repository any more.");
    for (const path of unused) {
      console.log(`  ${path}`);
      console.log(`    category: ${byPath.get(path).category}`);
      console.log(`    reason on file: ${byPath.get(path).reason}`);
    }
  }

  listLineCitations();
}

function listLineCitations() {
  const { scanned, occurrences, sites } = scanLineCitations();
  const { byKey } = loadLineLedger();

  const buckets = new Map(LINE_CATEGORIES.map((c) => [c, []]));
  buckets.set("unlisted", []);
  for (const site of sortLedgerEntries([...sites.values()])) {
    const entry = byKey.get(lineCitationKey(site.source, site.cite));
    buckets.get(entry ? entry.category : "unlisted").push(site);
  }

  console.log("");
  console.log(
    `[check-doc-citations] line citations: ${scanned} source files scanned, ` +
      `${occurrences} citation(s) at ${sites.size} site(s)`
  );
  for (const [category, list] of buckets) {
    if (list.length === 0) continue;
    console.log("");
    console.log(`## line/${category} (${list.length})`);
    for (const site of list) {
      console.log(`  ${site.source}:${site.lines.join(",")} cites ${site.cite}`);
    }
  }
}

function runSelftest() {
  const file = resolve(ROOT, CORPUS_FILE);
  if (!existsSync(file)) fail(`${CORPUS_FILE} not found`);
  let corpus;
  try {
    corpus = JSON.parse(readFileSync(file, "utf-8"));
  } catch (err) {
    fail(`${CORPUS_FILE} is not valid JSON: ${err.message}`);
  }
  const trackedSet = new Set(corpus.tracked);
  const failures = [];

  for (const testCase of corpus.cases) {
    const refs = extractFromLine(testCase.line);
    const actual = refs.map((ref) => ({
      ref,
      via: resolveReference(ref, testCase.source, trackedSet),
    }));
    const expected = testCase.expect.map((e) => ({ ref: e.ref, via: e.via }));
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      failures.push({ id: testCase.id, expected, actual });
    }
  }

  const lineIndex = buildTrackedIndex(corpus.lineTracked ?? corpus.tracked);
  for (const testCase of corpus.lineCases ?? []) {
    const index = lineIndex;
    const actual = extractLineCitationsFromLine(testCase.line).map((cite) => ({
      cite,
      category: classifyLineCitation(cite.slice(0, cite.lastIndexOf(":")), index),
    }));
    const expected = testCase.expect.map((e) => ({ cite: e.cite, category: e.category }));
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      failures.push({ id: testCase.id, expected, actual });
    }
  }

  for (const testCase of corpus.allowlistCases) {
    const actual = findUnusedAllowEntries(testCase.allow, testCase.unresolvedRefs);
    const expected = testCase.expectUnused;
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      failures.push({ id: testCase.id, expected, actual });
    }
  }

  for (const f of failures) {
    console.error(`[check-doc-citations] selftest FAIL ${f.id}`);
    console.error(`  expected ${JSON.stringify(f.expected)}`);
    console.error(`  actual   ${JSON.stringify(f.actual)}`);
  }

  const total =
    corpus.cases.length + (corpus.lineCases ?? []).length + corpus.allowlistCases.length;
  if (failures.length > 0) {
    console.error(`[check-doc-citations] selftest: ${total - failures.length}/${total} passed`);
    process.exit(1);
  }
  console.log(`[check-doc-citations] selftest: ${total}/${total} corpus cases passed`);
}

// --------------------------------------------------------------------------

const args = process.argv.slice(2);
const unknown = args.filter(
  (a) => !["--list", "--selftest", "--write-line-ledger"].includes(a)
);
if (unknown.length > 0) {
  console.error(`[check-doc-citations] unknown argument(s): ${unknown.join(", ")}`);
  console.error(
    "  usage: node scripts/check-doc-citations.mjs [--list | --selftest | --write-line-ledger]"
  );
  process.exit(2);
}

if (args.includes("--selftest")) {
  runSelftest();
} else if (args.includes("--write-line-ledger")) {
  runWriteLineLedger();
} else if (args.includes("--list")) {
  runList();
} else {
  runCheck();
}
