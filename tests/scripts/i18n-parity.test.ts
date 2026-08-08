/**
 * scripts/i18n-parity.mjs: the What's New stamp check, and the rules applied to
 * the translated bullets.
 *
 * The structural half of this script (key sets, empty values) predates the
 * What's New work. What is pinned here is the half that exists because nothing
 * else could see it: a locale whose highlights still carry the previous
 * wording has the same key count and the same non-empty values, so only the
 * highlightsStamp comparison can tell it apart from a fresh translation.
 *
 * Each case runs the real script against a throwaway repo (see
 * ./script-fixture); this repository's src/locales/ is never read or written.
 *
 * Those cases are all child processes and never touch a DOM, so this file opts
 * out of the project-wide jsdom environment and skips booting it.
 *
 * @vitest-environment node
 */
import { afterEach, describe, expect, it } from "vitest";
import { createFixtureRepo, type FixtureRepo } from "./script-fixture";

const STAMP = "9.9.9+1a2b3c4d";
const PREVIOUS_STAMP = "9.9.8+99887766";

const ARCHIVE_STAMPS = { "9.9.9": "1a2b3c4d", "9.9.8": "99887766" };

interface Locale {
  whatsNewDialog: {
    title: string;
    highlights: string[];
    highlightsStamp?: string;
    releases?: Record<string, string[]>;
    releaseStamps?: Record<string, string>;
  };
}

function english(): Locale {
  return {
    whatsNewDialog: {
      title: "What is new",
      highlights: ["The plate the operator points at is the one that runs."],
      highlightsStamp: STAMP,
      releases: {
        "9.9.9": ["The plate the operator points at is the one that runs."],
        "9.9.8": ["The previous release note."],
      },
      releaseStamps: { ...ARCHIVE_STAMPS },
    },
  };
}

function korean(): Locale {
  return {
    whatsNewDialog: {
      title: "새로운 기능",
      highlights: ["지정한 플레이트가 실행 대상이 된다."],
      highlightsStamp: STAMP,
      releases: {
        "9.9.9": ["지정한 플레이트가 실행 대상이 된다."],
        "9.9.8": ["직전 릴리스 항목."],
      },
      releaseStamps: { ...ARCHIVE_STAMPS },
    },
  };
}

let repo: FixtureRepo | undefined;

/** Fixture repo holding src/locales/en.json plus one translated locale. */
function fixture(en: Locale, ko: Locale): FixtureRepo {
  const created = createFixtureRepo();
  repo = created;
  created.writeJson("src/locales/en.json", en);
  created.writeJson("src/locales/ko.json", ko);
  return created;
}

afterEach(() => {
  repo?.cleanup();
  repo = undefined;
});

describe("i18n-parity", () => {
  it("passes when every locale carries en's stamp and clean translations", () => {
    const fx = fixture(english(), korean());

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(0);
    expect(run.output).toContain("i18n-parity: ok");
  });

  it("fails a locale still holding the previous release's stamp", () => {
    const stale = korean();
    stale.whatsNewDialog.highlightsStamp = PREVIOUS_STAMP;
    const fx = fixture(english(), stale);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("highlightsStamp");
    expect(run.output).toContain("ko");
    expect(run.output).toContain(STAMP);
  });

  it("fails when en.json has no stamp at all, so nothing can judge the translations", () => {
    const en = english();
    const ko = korean();
    delete en.whatsNewDialog.highlightsStamp;
    delete ko.whatsNewDialog.highlightsStamp;
    const fx = fixture(en, ko);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("en.json has no whatsNewDialog.highlightsStamp");
  });

  it("names the archived release a locale is behind on, and only that one", () => {
    // A past release reworded in the CHANGELOG moves its own digest. The locale
    // still shows those bullets whenever someone skips that release, so the
    // check has to point at the version rather than at the file as a whole.
    const ko = korean();
    ko.whatsNewDialog.releaseStamps = { ...ARCHIVE_STAMPS, "9.9.8": "00000000" };
    const fx = fixture(english(), ko);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("releaseStamps");
    expect(run.output).toContain("9.9.8");
    expect(run.output).not.toContain("- ko: 9.9.9");
  });

  it("fails an archived translation containing a backtick", () => {
    // The archive is rendered by the same modal, so the same rules hold there.
    const ko = korean();
    ko.whatsNewDialog.releases = {
      ...(ko.whatsNewDialog.releases ?? {}),
      "9.9.8": ["`analyze_run_folder` 호출이 수율을 반환한다."],
    };
    const fx = fixture(english(), ko);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("releases.9.9.8");
    expect(run.output).toContain("backtick");
  });

  it("fails when en.json has no archive stamps at all", () => {
    const en = english();
    const ko = korean();
    delete en.whatsNewDialog.releaseStamps;
    delete ko.whatsNewDialog.releaseStamps;
    const fx = fixture(en, ko);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("en.json has no whatsNewDialog.releaseStamps");
  });

  it("fails a translated bullet containing a backtick", () => {
    const ko = korean();
    ko.whatsNewDialog.highlights = ["`analyze_run_folder` 호출이 수율을 반환한다."];
    const fx = fixture(english(), ko);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("backtick");
  });

  it("fails a translated bullet over 200 characters and reports its actual length", () => {
    const ko = korean();
    ko.whatsNewDialog.highlights = ["가".repeat(201)];
    const fx = fixture(english(), ko);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("201 chars");
    expect(run.output).toContain("max 200");
  });
});
