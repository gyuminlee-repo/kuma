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
 * Usage:
 *   node scripts/check-doc-citations.mjs            check, exit 1 on a new unresolved citation
 *   node scripts/check-doc-citations.mjs --list     report every unresolved citation, never fails
 *   node scripts/check-doc-citations.mjs --selftest run the labelled corpus, exit 1 on a mismatch
 *
 * Exit codes: 0 clean, 1 check or selftest failed, 2 the checker itself could not run.
 *
 * Node standard library only, matching the rest of scripts/.
 */

import { spawnSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve, posix as posixPath } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ALLOWLIST_FILE = "scripts/doc-citations-allow.json";
const CORPUS_FILE = "scripts/check-doc-citations.corpus.json";

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
const SELF_EXCLUDED = new Set([ALLOWLIST_FILE, CORPUS_FILE]);

/** mkdocs resolves nav and exclude entries against docs_dir, so that root is tried too. */
const DOCS_DIR = "docs";

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

  const fromDocs = insideRoot(posixPath.join(DOCS_DIR, ref));
  if (fromDocs && trackedSet.has(fromDocs)) return "docs";

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

  if (offenders.length > 0 || unused.length > 0) process.exit(1);

  console.log(
    `[check-doc-citations] OK: ${scanned} files scanned, ${occurrences} citations, ` +
      `${allowedRefs} unresolved reference(s), all accounted for in ${ALLOWLIST_FILE}, ` +
      `and every allowlist entry still describes a live citation`
  );
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

  const total = corpus.cases.length + corpus.allowlistCases.length;
  if (failures.length > 0) {
    console.error(`[check-doc-citations] selftest: ${total - failures.length}/${total} passed`);
    process.exit(1);
  }
  console.log(`[check-doc-citations] selftest: ${total}/${total} corpus cases passed`);
}

// --------------------------------------------------------------------------

const args = process.argv.slice(2);
const unknown = args.filter((a) => !["--list", "--selftest"].includes(a));
if (unknown.length > 0) {
  console.error(`[check-doc-citations] unknown argument(s): ${unknown.join(", ")}`);
  console.error("  usage: node scripts/check-doc-citations.mjs [--list | --selftest]");
  process.exit(2);
}

if (args.includes("--selftest")) {
  runSelftest();
} else if (args.includes("--list")) {
  runList();
} else {
  runCheck();
}
