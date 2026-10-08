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
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  BUILD_EVOLVEPRO_STORAGE_KEY,
  loadBuildEvolveproFromStorage,
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
