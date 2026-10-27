/**
 * buildEvolveproFormStorage.test.ts
 *
 * Regression coverage for defect 2 (see AGENTS.md task notes, "MAME sample
 * data triplicate"): a legacy global record (`kuma:mame:buildEvolvepro`, no
 * `:v2:<project>` suffix) that carries none of the `LEGACY_PATH_KEYS` paths
 * used to be read as "belongs to no project" (`paths.length > 0 && ...` was
 * false on an empty array), forcing `migrationNotice: true` on every project
 * that reads it. `seedBuildEvolveproForm` bails out on `migrationNotice`, so
 * `loadSampleData()` silently stopped seeding step 4 and the panel was stuck
 * on "Unsupported saved mode" with no in-app recovery.
 *
 * An empty-paths record states nothing about which project it belongs to; it
 * is not evidence of belonging to a *different* one, so it should be adopted
 * (which costs nothing, since there are no foreign paths to inherit) rather
 * than rejected.
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  applyBuildEvolveproPatch,
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  hasBuildEvolveproFormValues,
  BUILD_EVOLVEPRO_STORAGE_KEY,
  hasBuildEvolveproConfirmationInputs,
  loadBuildEvolveproFromStorage,
  saveBuildEvolveproToStorage,
  seedBuildEvolveproForm,
} from "./buildEvolveproFormStorage";

const PROJECT = "/project";

describe("loadBuildEvolveproFromStorage, empty-paths legacy record (defect 2)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("adopts a legacy record with no stored paths instead of flagging migrationNotice", () => {
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify({
        primarySource: "longFormat",
        confirmationSource: "none",
        verdictXlsx: "",
        outputXlsx: "",
      }),
    );

    const state = loadBuildEvolveproFromStorage(PROJECT);

    expect(state.migrationNotice).toBe(false);
  });

  it("still rejects a legacy record whose paths point at a different project", () => {
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify({
        activityPath: "/other-project/activity.csv",
        verdictXlsx: "/other-project/verdict.xlsx",
        outputXlsx: "/other-project/output.xlsx",
      }),
    );

    const state = loadBuildEvolveproFromStorage(PROJECT);

    expect(state.migrationNotice).toBe(true);
  });

  it("lets seedBuildEvolveproForm populate step 4 after adopting an empty-paths legacy record", () => {
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify({
        primarySource: "longFormat",
        confirmationSource: "none",
      }),
    );

    // Before the fix this was a silent no-op: seedBuildEvolveproForm's first
    // line reads storage, sees migrationNotice: true, and returns.
    seedBuildEvolveproForm({ activityPath: "/project/sample/activity.csv" }, PROJECT);

    const state = loadBuildEvolveproFromStorage(PROJECT);
    expect(state.migrationNotice).toBe(false);
    expect(state.activityPath).toBe("/project/sample/activity.csv");
  });

  it("leaves a fresh project (no legacy or scoped record) on the untouched default", () => {
    expect(loadBuildEvolveproFromStorage(PROJECT)).toEqual(BUILD_EVOLVEPRO_DEFAULT_STATE);
  });
});

describe("confirmation sources saved before well labels existed", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const SCOPED_KEY = `${BUILD_EVOLVEPRO_STORAGE_KEY}:v2:${encodeURIComponent(PROJECT)}`;

  it.each(["none", "variantLabels", "numericIds"] as const)(
    "still loads a %s form written by the previous release, with no well path",
    (confirmationSource) => {
      localStorage.setItem(
        SCOPED_KEY,
        JSON.stringify({
          version: 2,
          projectPath: PROJECT,
          primarySource: "rawReport",
          confirmationSource,
          round1ReportXlsx: "/project/activity/report.xlsx",
          remeasureReportXlsx: "/project/activity/wells.xlsx",
          remeasureNumericXlsx: "/project/activity/numeric.xlsx",
          verdictXlsx: "",
          outputXlsx: "",
        }),
      );

      const state = loadBuildEvolveproFromStorage(PROJECT);

      expect(state.migrationNotice).toBe(false);
      expect(state.confirmationSource).toBe(confirmationSource);
      expect(state.remeasureWellXlsx).toBe("");
      expect(state.remeasureReportXlsx).toBe("/project/activity/wells.xlsx");
    },
  );

  it("round-trips a wellLabels form and seeds it from a well path", () => {
    saveBuildEvolveproToStorage(
      { ...BUILD_EVOLVEPRO_DEFAULT_STATE, confirmationSource: "wellLabels", remeasureWellXlsx: "/project/activity/rep.xlsx" },
      PROJECT,
    );
    expect(loadBuildEvolveproFromStorage(PROJECT)).toMatchObject({
      migrationNotice: false, confirmationSource: "wellLabels", remeasureWellXlsx: "/project/activity/rep.xlsx",
    });

    localStorage.clear();
    seedBuildEvolveproForm({ remeasureWellXlsx: "/project/sample/rep.xlsx" }, PROJECT);
    expect(loadBuildEvolveproFromStorage(PROJECT)).toMatchObject({
      confirmationSource: "wellLabels", remeasureWellXlsx: "/project/sample/rep.xlsx",
    });
  });

  it("is only complete once the chosen kind has its path", () => {
    const base = { ...BUILD_EVOLVEPRO_DEFAULT_STATE, confirmationSource: "wellLabels" as const };
    expect(hasBuildEvolveproConfirmationInputs(base)).toBe(false);
    expect(hasBuildEvolveproConfirmationInputs({ ...base, remeasureWellXlsx: "/project/a.xlsx" })).toBe(true);
  });
});


describe("unticked review rows", () => {
  const row = { source: "round1_report_xlsx" as const, row_index: 23, block_index: 5, sample_name: "WT4", area: 40 };
  const reviewed = {
    ...BUILD_EVOLVEPRO_DEFAULT_STATE,
    primarySource: "rawReport" as const,
    round1ReportXlsx: "/project/r.xlsx",
    verdictXlsx: "/project/v.xlsx",
    excludedRows: [row],
  };

  beforeEach(() => {
    localStorage.clear();
  });

  it("loads a save from before the review existed with nothing unticked", () => {
    localStorage.setItem(
      `${BUILD_EVOLVEPRO_STORAGE_KEY}:v2:${encodeURIComponent(PROJECT)}`,
      JSON.stringify({ primarySource: "rawReport", round1ReportXlsx: "/project/r.xlsx" }),
    );
    const state = loadBuildEvolveproFromStorage(PROJECT);
    expect(state.excludedRows).toEqual([]);
    expect(state.round1ReportXlsx).toBe("/project/r.xlsx");
  });

  it("round-trips unticked rows and drops malformed ones", () => {
    saveBuildEvolveproToStorage(reviewed, PROJECT);
    expect(loadBuildEvolveproFromStorage(PROJECT).excludedRows).toEqual([row]);
    const key = `${BUILD_EVOLVEPRO_STORAGE_KEY}:v2:${encodeURIComponent(PROJECT)}`;
    const saved = JSON.parse(localStorage.getItem(key) ?? "{}");
    saved.excludedRows = [row, { source: "nowhere", row_index: 1, sample_name: "x" }, { ...row, row_index: "23" }, "junk"];
    localStorage.setItem(key, JSON.stringify(saved));
    expect(loadBuildEvolveproFromStorage(PROJECT).excludedRows).toEqual([row]);
  });

  it("empties them when an input the review was read from changes", () => {
    for (const patch of [
      { round1ReportXlsx: "/project/other.xlsx" },
      { layoutXlsx: "/project/layout.xlsx" },
      { verdictXlsx: "/project/v2.xlsx" },
      { expectedXlsx: "/project/expected.xlsx" },
      { confirmationSource: "wellLabels" as const, remeasureWellXlsx: "/project/c.xlsx" },
    ]) {
      expect(applyBuildEvolveproPatch(reviewed, patch).excludedRows).toEqual([]);
    }
  });

  it("keeps them when the same value is picked again or an unrelated field changes", () => {
    expect(applyBuildEvolveproPatch(reviewed, { round1ReportXlsx: "/project/r.xlsx" }).excludedRows).toEqual([row]);
    expect(applyBuildEvolveproPatch(reviewed, { outputXlsx: "/project/out.xlsx" }).excludedRows).toEqual([row]);
    expect(applyBuildEvolveproPatch(reviewed, { mismatchThreshold: 0.2 }).excludedRows).toEqual([row]);
  });

  it("takes an explicit selection as given", () => {
    expect(applyBuildEvolveproPatch(reviewed, { excludedRows: [] }).excludedRows).toEqual([]);
  });

  it("does not count an empty selection as a restored value", () => {
    expect(hasBuildEvolveproFormValues({ ...BUILD_EVOLVEPRO_DEFAULT_STATE, excludedRows: [] })).toBe(false);
    expect(hasBuildEvolveproFormValues({ ...BUILD_EVOLVEPRO_DEFAULT_STATE, excludedRows: [row] })).toBe(true);
  });
});
