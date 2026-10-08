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

// ═══════════════════════════════════════════════════════════════════════════
// Interpolation checks
//
// The checks above compare key sets and the What's New stamps. A key can be
// present in every locale, non-empty everywhere, stamped current, and still
// render wrong, because the part carrying the number or the filename is the
// `{{placeholder}}` inside the value and nothing looked at it.
//
// Every case below is built from fixtures rather than from src/locales/, on
// purpose: the shipping bundle currently trips all of these, and the change that
// repairs the strings would delete any test pinned to those particular defects.
// ═══════════════════════════════════════════════════════════════════════════

const INTERP_STAMP = "9.9.9+abcdef01";
const INTERP_ARCHIVE = { "9.9.9": "abcdef01" };

/** Reference bundle: one key per defect class the interpolation checks cover. */
function interpEn(): Record<string, unknown> {
  return {
    whatsNewDialog: {
      title: "What is new",
      highlights: ["The plate the operator points at is the one that runs."],
      highlightsStamp: INTERP_STAMP,
      releases: { "9.9.9": ["The plate the operator points at is the one that runs."] },
      releaseStamps: { ...INTERP_ARCHIVE },
    },
    job: {
      deadlock: "No progress update for {{seconds}}+ seconds.",
      designed: "{{success}}/{{total}} primers designed",
      daysAgo: "{{count}} day(s) ago",
      minutesAgo: "{{n}} min ago",
      // Plural family, CLDR suffixes. i18next supplies `count` itself here.
      plates_one: "{{count}} plate",
      plates_other: "{{count}} plates",
      // Plural family whose base key carries no suffix, the shape
      // parameterPanel.plateCount uses in this repo.
      plateCount: "{{count}} plate",
      plateCount_other: "{{count}} plates",
    },
  };
}

/** A correct translation of the above: same placeholders, different prose. */
function interpXx(): Record<string, unknown> {
  return {
    whatsNewDialog: {
      title: "Neuerungen",
      highlights: ["Die angezeigte Platte ist die, die laeuft."],
      highlightsStamp: INTERP_STAMP,
      releases: { "9.9.9": ["Die angezeigte Platte ist die, die laeuft."] },
      releaseStamps: { ...INTERP_ARCHIVE },
    },
    job: {
      deadlock: "Kein Fortschritt seit {{seconds}} Sekunden.",
      designed: "{{success}}/{{total}} Primer entworfen",
      daysAgo: "vor {{count}} Tagen",
      minutesAgo: "vor {{n}} Minuten",
      plates_one: "{{count}} Platte",
      plates_other: "{{count}} Platten",
      plateCount: "{{count}} Platte",
      plateCount_other: "{{count}} Platten",
    },
  };
}

/**
 * Fixture repo with en.json, one translated locale, and optionally a source
 * file so the caller-side check has call sites to read. The locale is named
 * `xx` so it has no UNTRANSLATED_BASELINE entry and is therefore budgeted at
 * zero: a fixture carries no shipping debt, so any English left in place is
 * growth and must fail.
 */
function interpFixture(
  en: Record<string, unknown>,
  xx: Record<string, unknown>,
  source?: { path: string; contents: string },
): FixtureRepo {
  const created = createFixtureRepo();
  repo = created;
  created.writeJson("src/locales/en.json", en);
  created.writeJson("src/locales/xx.json", xx);
  if (source) created.write(source.path, source.contents);
  return created;
}

describe("i18n-parity interpolation checks", () => {
  it("passes a bundle whose placeholders and call sites all line up", () => {
    const fx = interpFixture(interpEn(), interpXx(), {
      path: "src/screens/Shell.tsx",
      contents: [
        'const a = t("job.deadlock", { seconds: 300 });',
        'const b = t("job.designed", { success: 12, total: 96 });',
        'const c = t("job.daysAgo", { count: 3 });',
        'const d = t("job.minutesAgo", { n: 5 });',
        // Plural families: `count` is i18next's own option, not an
        // interpolation variable the caller has to be credited for.
        'const e = t("job.plates", { count: 2 });',
        'const f = t("job.plateCount", { count: 2 });',
        "",
      ].join("\n"),
    });

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(0);
    expect(run.output).toContain("i18n-parity: ok");
  });

  it("class A: fails a locale that dropped a placeholder and hardcoded the value", () => {
    // DEADLOCK_THRESHOLD_MS moves and the string keeps claiming 30 seconds.
    const xx = interpXx();
    (xx.job as Record<string, string>).deadlock = "Kein Fortschritt seit 30 Sekunden.";
    const fx = interpFixture(interpEn(), xx);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("placeholder mismatch vs en");
    expect(run.output).toContain("job.deadlock");
    expect(run.output).toContain("dropped {{seconds}}");
  });

  it("class B: fails a locale whose placeholder identifier was translated too", () => {
    // The caller still passes `success`, so i18next cannot substitute and the
    // reader gets the literal token where the count belongs.
    const xx = interpXx();
    (xx.job as Record<string, string>).designed = "{{Erfolg}}/{{total}} Primer entworfen";
    const fx = interpFixture(interpEn(), xx);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("job.designed");
    expect(run.output).toContain("dropped {{success}}");
    expect(run.output).toContain("renamed/added {{Erfolg}}");
  });

  it("class C: fails a call site that does not supply the placeholder its key needs", () => {
    // Every locale agrees here, so no cross-locale comparison can see it. Only
    // the interpolation object at the call site can.
    const fx = interpFixture(interpEn(), interpXx(), {
      path: "src/screens/Shell.tsx",
      contents: 'const c = t("job.daysAgo", { n: Math.floor(diffHr / 24) });\n',
    });

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("call site does not supply a placeholder");
    expect(run.output).toContain("src/screens/Shell.tsx:1");
    expect(run.output).toContain("job.daysAgo");
    expect(run.output).toContain("needs {{count}}");
  });

  it("class C: does not flag {{count}} in a plural family, in either key shape", () => {
    // i18next passes `count` to the interpolator itself for a plural family, so
    // a rule that demanded it in the options object would fail every plural key
    // in the bundle. Both shapes present in this repo are covered: `_one`/
    // `_other`, and a bare base key with an `_other` sibling.
    const fx = interpFixture(interpEn(), interpXx(), {
      path: "src/screens/Shell.tsx",
      contents: [
        'const e = t("job.plates", { count: 2 });',
        'const f = t("job.plateCount", { count: 2 });',
        "",
      ].join("\n"),
    });

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(0);
    expect(run.output).not.toContain("call site does not supply a placeholder");
  });

  it("class C: reports the call shapes it cannot resolve instead of omitting them", () => {
    // A check that silently covers only some call sites is the defect class it
    // exists to catch, so the gaps are named on every run, pass or fail.
    const fx = interpFixture(interpEn(), interpXx(), {
      path: "src/screens/Shell.tsx",
      contents: [
        "const a = t(`job.${which}`);",
        'const b = t("job.designed", { ...counts });',
        "",
      ].join("\n"),
    });

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(0);
    expect(run.output).toContain("1 dynamic-key call(s)");
    expect(run.output).toContain("dynamic key: src/screens/Shell.tsx:1");
    expect(run.output).toContain("opaque options: src/screens/Shell.tsx:2");
  });

  it("class D: fails a null value and a whitespace-only value, which `v === \"\"` missed", () => {
    const xx = interpXx();
    (xx.job as Record<string, unknown>).deadlock = null;
    (xx.job as Record<string, unknown>).designed = "   ";
    const fx = interpFixture(interpEn(), xx);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("xx empty values: 2");
    expect(run.output).toContain("job.deadlock");
    expect(run.output).toContain("job.designed");
  });

  it("class E: fails a locale carrying more English-identical values than its baseline", () => {
    // The ratchet, not a hard rule about the stock. `xx` has no baseline entry
    // and is therefore budgeted at zero, which is what a brand new locale
    // committed as a copy of en.json looks like.
    const xx = interpXx();
    (xx.job as Record<string, string>).designed = "{{success}}/{{total}} primers designed";
    const fx = interpFixture(interpEn(), xx);

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(1);
    expect(run.output).toContain("untranslated value(s), baseline 0");
    expect(run.output).toContain("job.designed");
    expect(run.output).toContain("UNTRANSLATED_BASELINE");
  });

  it("class E: reports the count on a passing run so it cannot drift unnoticed", () => {
    const fx = interpFixture(interpEn(), interpXx());

    const run = fx.run("i18n-parity.mjs");

    expect(run.status).toBe(0);
    expect(run.output).toContain("untranslated (value byte-identical to en");
    expect(run.output).toContain("xx: 0 / baseline 0");
  });
});
