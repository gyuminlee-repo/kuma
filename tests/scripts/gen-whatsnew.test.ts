/**
 * scripts/gen-whatsnew.mjs: CHANGELOG parser, authoring rules, stamp, exit codes.
 *
 * This runs on every release (pnpm sync:check, .githooks/pre-push, CI) and a
 * failure here blocks the tag, so the behaviour worth pinning is the contract
 * its callers read: which exit code means "the CHANGELOG is not ready" (2)
 * versus "someone wrote a bullet that breaks the rules" (1), and that the stamp
 * moves on any wording edit rather than only at a version boundary, since that
 * is the whole reason the stamp exists.
 *
 * Every case runs the real script against a throwaway repo (see
 * ./script-fixture), never against this repository's CHANGELOG.md,
 * package.json or src/locales/.
 *
 * Those cases are all child processes and never touch a DOM, so this file opts
 * out of the project-wide jsdom environment and skips booting it.
 *
 * @vitest-environment node
 */
import { afterEach, describe, expect, it } from "vitest";
import { createFixtureRepo, type FixtureRepo } from "./script-fixture";

const VERSION = "9.9.9";
const STAMP_PATTERN = /^9\.9\.9\+[0-9a-f]{8}$/;

interface EnLocale {
  whatsNewDialog: {
    highlights?: unknown;
    highlightsStamp?: unknown;
    releases?: Record<string, string[]>;
    releaseStamps?: Record<string, string>;
  };
}

/** A CHANGELOG whose latest section carries the given "### Highlights" lines. */
function changelog(highlightLines: string[], version = VERSION): string {
  return [
    `## v${version} (2026-01-01)`,
    "",
    "One paragraph of intro prose that the generator ignores.",
    "",
    "### Highlights",
    ...highlightLines,
    "",
    "### Added",
    "- an internal change that is not a highlight",
    "",
    "## v9.9.8 (2025-12-31)",
    "",
    "### Highlights",
    "- the previous release note",
    "",
  ].join("\n");
}

let repo: FixtureRepo | undefined;

/** Fixture repo holding package.json, CHANGELOG.md and a minimal en.json. */
function fixture(changelogText: string): FixtureRepo {
  const created = createFixtureRepo();
  repo = created;
  created.writeJson("package.json", { name: "kuma-fixture", version: VERSION });
  created.write("CHANGELOG.md", changelogText);
  created.writeJson("src/locales/en.json", {
    whatsNewDialog: {
      title: "What is new in v{{version}}",
      highlights: ["stale wording from an earlier release"],
      highlightsStamp: "0.0.0+deadbeef",
    },
  });
  return created;
}

afterEach(() => {
  repo?.cleanup();
  repo = undefined;
});

describe("gen-whatsnew", () => {
  it("writes the highlights and a version+digest stamp into en.json", () => {
    const fx = fixture(changelog(["- The plate the operator points at is the one that runs.", "- Cancelling a run leaves the previous results in place."]));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(0);
    const en = fx.readJson<EnLocale>("src/locales/en.json");
    expect(en.whatsNewDialog.highlights).toEqual([
      "The plate the operator points at is the one that runs.",
      "Cancelling a run leaves the previous results in place.",
    ]);
    expect(en.whatsNewDialog.highlightsStamp).toMatch(STAMP_PATTERN);
  });

  it("archives every section that has a Highlights block, newest first", () => {
    // The fixture CHANGELOG carries a second, older section with its own block.
    // The modal shows every release an operator skipped, so both have to be in
    // the archive and in the order they are rendered.
    const fx = fixture(changelog(["- The plate the operator points at is the one that runs."]));

    expect(fx.run("gen-whatsnew.mjs").status).toBe(0);

    const dialog = fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog;
    expect(Object.keys(dialog.releases ?? {})).toEqual([VERSION, "9.9.8"]);
    expect(dialog.releases?.[VERSION]).toEqual([
      "The plate the operator points at is the one that runs.",
    ]);
    expect(dialog.releases?.["9.9.8"]).toEqual(["the previous release note"]);
    // The newest archive entry and the standalone highlights are one release.
    expect(dialog.releases?.[VERSION]).toEqual(dialog.highlights);
    expect(Object.keys(dialog.releaseStamps ?? {})).toEqual([VERSION, "9.9.8"]);
    for (const digest of Object.values(dialog.releaseStamps ?? {})) {
      expect(digest).toMatch(/^[0-9a-f]{8}$/);
    }
  });

  it("moves only the reworded past release's digest, and fails --check", () => {
    // Rewording a shipped release is what the per-version digests exist to
    // catch: the nine translations of that one release are now behind, and
    // nothing else is.
    const fx = fixture(changelog(["- The plate the operator points at is the one that runs."]));
    expect(fx.run("gen-whatsnew.mjs").status).toBe(0);
    const before = fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog.releaseStamps ?? {};

    fx.write(
      "CHANGELOG.md",
      changelog(["- The plate the operator points at is the one that runs."]).replace(
        "- the previous release note",
        "- the previous release notes",
      ),
    );

    const check = fx.run("gen-whatsnew.mjs", ["--check"]);
    expect(check.status).toBe(1);
    expect(check.output).toContain("releases");

    expect(fx.run("gen-whatsnew.mjs").status).toBe(0);
    const after = fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog.releaseStamps ?? {};
    expect(after["9.9.8"]).not.toBe(before["9.9.8"]);
    expect(after[VERSION]).toBe(before[VERSION]);
  });

  it("passes --check on the en.json it just wrote", () => {
    const fx = fixture(changelog(["- The plate the operator points at is the one that runs."]));
    expect(fx.run("gen-whatsnew.mjs").status).toBe(0);

    const check = fx.run("gen-whatsnew.mjs", ["--check"]);

    expect(check.status).toBe(0);
    expect(check.output).toContain("up to date");
  });

  it("moves the stamp digest and fails --check when one character of a bullet changes", () => {
    const fx = fixture(changelog(["- The plate the operator points at is the one that runs."]));
    fx.run("gen-whatsnew.mjs");
    const before = fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog.highlightsStamp;

    // One character, no version bump: exactly the edit a version-only stamp
    // would sleep through while nine translations describe the old wording.
    fx.write("CHANGELOG.md", changelog(["- The plate the operator points at is the one that ran."]));
    const check = fx.run("gen-whatsnew.mjs", ["--check"]);

    expect(check.status).toBe(1);
    expect(check.output).toContain("highlightsStamp");

    fx.run("gen-whatsnew.mjs");
    const after = fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog.highlightsStamp;
    expect(after).not.toBe(before);
    expect(after).toMatch(STAMP_PATTERN);
  });

  it("rejects a bullet over 140 characters and reports its actual length", () => {
    const long = `- ${"x".repeat(141)}`;
    const fx = fixture(changelog([long]));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("141 chars");
    expect(run.output).toContain("max 140");
  });

  it("rejects a bullet containing a backtick", () => {
    const fx = fixture(changelog(["- The `analyze_run_folder` call now returns the yield."]));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("backtick");
  });

  it("exits 2 when the latest section has no Highlights block", () => {
    const fx = fixture(
      ["## v9.9.9 (2026-01-01)", "", "Intro prose only.", "", "### Added", "- something", ""].join("\n"),
    );

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(2);
    expect(run.output).toContain("no '### Highlights' block");
  });

  it("exits 2 when the Highlights block has no bullets", () => {
    const fx = fixture(changelog(["(notes to be written)"]));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(2);
    expect(run.output).toContain("no bullets");
  });

  it("exits 2 when the latest section is a different release", () => {
    const fx = fixture(changelog(["- A note written for the release before this one."], "9.9.8"));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(2);
    expect(run.output).toContain("is v9.9.8");
    expect(run.output).toContain("9.9.9");
  });

  // ---- which version identifies a release ---------------------------------
  //
  // Two versions live in this repo. package.json, Cargo.toml and
  // tauri.conf.json carry three parts because Tauri and Cargo enforce SemVer
  // 2.0, and they identify the binary (scripts/rename-bundle-to-tag.mjs states
  // the rule). A release is the four-part vA.BB.CC.DD tag of the commit
  // convention, which is what the CHANGELOG headings use, what the keys of
  // `releases`/`releaseStamps` are, and what vite.config.ts resolves
  // __APP_VERSION__ to from `git describe` and the modal compares against. The
  // stamp belongs to the second namespace: stamping the three-part version
  // cannot tell 0.16.25 from 0.16.25.1, and that is how v0.16.25.1 shipped its
  // bullets stamped "0.16.25+291c60a5" in all ten locales with every gate green.

  it("stamps a DD release with the release version, not the package version", () => {
    const fx = fixture(changelog(["- A note that belongs to the DD release."], "9.9.9.1"));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(0);
    const dialog = fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog;
    expect(dialog.highlightsStamp).toMatch(/^9\.9\.9\.1\+[0-9a-f]{8}$/);
    // The two halves of the stamp are exactly a key of releaseStamps and that
    // key's value. Under the three-part stamp they were not, which is what left
    // the archive and the stamp naming different releases.
    const [stampVersion, stampDigest] = String(dialog.highlightsStamp).split("+");
    expect(dialog.releaseStamps?.[stampVersion]).toBe(stampDigest);
    expect(dialog.releases?.[stampVersion]).toEqual(dialog.highlights);
  });

  it("exits 2 when the latest section only shares a version prefix", () => {
    // "v9.9.9" is a prefix of "v9.9.9.1" and of nothing else that matters here,
    // but the reverse direction is the trap: a substring freshness test accepts
    // any heading the current version is a prefix of, including another
    // release. The guard compares version parts instead.
    const fx = fixture(changelog(["- A note for a release two steps ahead."], "9.9.90"));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(2);
    expect(run.output).toContain("is v9.9.90");
  });

  it("exits 2 when the latest heading declares no version at all", () => {
    // The section body names the current version in prose, which satisfied the
    // substring test while the heading identified no release to stamp.
    const fx = fixture(
      [
        "## Unreleased",
        "",
        "Notes gathered toward v9.9.9.",
        "",
        "### Highlights",
        "- A note nobody can date.",
        "",
      ].join("\n"),
    );

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(2);
    expect(run.output).toContain("heading");
  });

  it("rejects a stamp that names the package version instead of the release", () => {
    const fx = fixture(changelog(["- A note that belongs to the DD release."], "9.9.9.1"));
    expect(fx.run("gen-whatsnew.mjs").status).toBe(0);

    const en = fx.readJson<EnLocale>("src/locales/en.json");
    const digest = String(en.whatsNewDialog.highlightsStamp).split("+")[1];
    en.whatsNewDialog.highlightsStamp = `9.9.9+${digest}`;
    fx.writeJson("src/locales/en.json", en);

    const check = fx.run("gen-whatsnew.mjs", ["--check"]);

    expect(check.status).toBe(1);
    expect(check.output).toContain("highlightsStamp");
    expect(check.output).toContain("9.9.9.1+");
  });

  it("joins a bullet wrapped over two lines into one highlight", () => {
    const fx = fixture(
      changelog([
        "- The plate the operator points at is the one that runs,",
        "  and the plate built for nobody is dropped.",
        "- A second, unwrapped note.",
      ]),
    );

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(0);
    expect(fx.readJson<EnLocale>("src/locales/en.json").whatsNewDialog.highlights).toEqual([
      "The plate the operator points at is the one that runs, and the plate built for nobody is dropped.",
      "A second, unwrapped note.",
    ]);
  });
});
