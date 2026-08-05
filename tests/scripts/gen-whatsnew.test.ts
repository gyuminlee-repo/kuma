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

  it("exits 2 when the latest section does not mention the current version", () => {
    const fx = fixture(changelog(["- A note written for the release before this one."], "9.9.8"));

    const run = fx.run("gen-whatsnew.mjs");

    expect(run.status).toBe(2);
    expect(run.output).toContain("does not mention current version v9.9.9");
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
