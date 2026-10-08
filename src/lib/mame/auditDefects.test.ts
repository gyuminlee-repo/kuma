import { beforeEach, describe, expect, it, vi } from "vitest";
import { exists, readTextFile } from "@tauri-apps/plugin-fs";
import {
  DEFAULT_JANUS_SETTINGS, JANUS_SETTINGS_STORAGE_KEY,
  loadJanusSettings, saveJanusSettings, toRpcParams,
} from "./janusSettings";
import {
  BUILD_EVOLVEPRO_DEFAULT_STATE, BUILD_EVOLVEPRO_STORAGE_KEY,
  loadBuildEvolveproFromStorage, saveBuildEvolveproToStorage, seedBuildEvolveproForm,
} from "./buildEvolveproFormStorage";
import { readMameResultSnapshot } from "./resultSnapshot";
import { sampleWells } from "./sampleData";
import { wellSortKey } from "./nbLabel";

vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: vi.fn(), readTextFile: vi.fn(), rename: vi.fn(),
}));

beforeEach(() => {
  localStorage.clear();
  vi.resetAllMocks();
});

describe("MAME-LIB-01 volume migration", () => {
  it("preserves a current explicit 100 through reload and RPC conversion", () => {
    saveJanusSettings({ ...DEFAULT_JANUS_SETTINGS, volume: 100 });
    expect(toRpcParams(loadJanusSettings()).volume).toBe(100);
  });

  it("migrates legacy 100 once and preserves a subsequent explicit 100", () => {
    localStorage.setItem(JANUS_SETTINGS_STORAGE_KEY, JSON.stringify({ volume: 100 }));
    expect(loadJanusSettings().volume).toBe(70);
    saveJanusSettings({ ...loadJanusSettings(), volume: 100 });
    expect(loadJanusSettings().volume).toBe(100);
  });
});

describe("MAME-LIB-02 project path identity", () => {
  it.each([
    ["/data/Project", "/data/project/activity.csv", "/data/project/activity.csv"],
    ["/data/Project", "/data/ProjectExtra/activity.csv", "/data/ProjectExtra/activity.csv"],
    ["/data/Project", "/data/Project/Activity.csv", "/data/Project/Activity.csv"],
    ["C:\\Data\\Project", "c:\\data\\project\\Activity.csv", "C:\\Data\\Project\\Activity.csv"],
    ["\\\\Server\\Share\\Project", "\\\\server\\share\\project\\Activity.csv", "\\\\Server\\Share\\Project\\Activity.csv"],
  ])("round-trips %s with input %s", (project, activityPath, expected) => {
    saveBuildEvolveproToStorage({ ...BUILD_EVOLVEPRO_DEFAULT_STATE, activityPath }, project);
    expect(loadBuildEvolveproFromStorage(project).activityPath).toBe(expected);
  });

  it("rejects foreign POSIX case in legacy adoption without removing the record", () => {
    const legacy = JSON.stringify({ activityPath: "/data/project/activity.csv" });
    localStorage.setItem(BUILD_EVOLVEPRO_STORAGE_KEY, legacy);
    expect(loadBuildEvolveproFromStorage("/data/Project").migrationNotice).toBe(true);
    expect(localStorage.getItem(BUILD_EVOLVEPRO_STORAGE_KEY)).toBe(legacy);
  });
});

describe("MAME-LIB-03 snapshot root", () => {
  it.each(["null", "[]", "42", "true", '"text"', "{}"])(
    "returns missing for JSON %s", async (text) => {
      vi.mocked(exists).mockResolvedValue(true);
      vi.mocked(readTextFile).mockResolvedValue(text);
      await expect(readMameResultSnapshot("/project")).resolves.toEqual({ status: "missing" });
    },
  );
});

describe("MAME-LIB-04 sample seeding", () => {
  it.each(["gcSheet", "rawReport", "numericReport"] as const)(
    "preserves the chosen %s mode even before its input is picked", (primarySource) => {
      saveBuildEvolveproToStorage({ ...BUILD_EVOLVEPRO_DEFAULT_STATE, primarySource }, "/project");
      seedBuildEvolveproForm({ activityPath: "/project/sample.csv" }, "/project");
      expect(loadBuildEvolveproFromStorage("/project").primarySource).toBe(primarySource);
    },
  );

  it("preserves a GC input and mode while filling empty sample fields", () => {
    saveBuildEvolveproToStorage({
      ...BUILD_EVOLVEPRO_DEFAULT_STATE, primarySource: "gcSheet", gcDataXlsx: "/project/real.xlsx",
    }, "/project");
    seedBuildEvolveproForm({ activityPath: "/project/sample.csv", gcDataXlsx: "/project/sample.xlsx" }, "/project");
    expect(loadBuildEvolveproFromStorage("/project")).toMatchObject({
      primarySource: "gcSheet", gcDataXlsx: "/project/real.xlsx", activityPath: "/project/sample.csv",
    });
  });

  it.each([
    [{ activityPath: "/project/sample.csv" }, "longFormat"],
    [{ gcDataXlsx: "/project/sample.xlsx" }, "gcSheet"],
    [{ round1ReportXlsx: "/project/sample.xlsx" }, "rawReport"],
    [{ numericReportXlsx: "/project/sample.xlsx" }, "numericReport"],
  ] as const)("selects the available sample source for a fresh form: %s", (paths, primarySource) => {
    seedBuildEvolveproForm(paths, "/project");
    expect(loadBuildEvolveproFromStorage("/project").primarySource).toBe(primarySource);
  });
});

describe("MAME-LIB-05 sample coordinates", () => {
  it("maps all 96 barcodes to their displayed wells using the R_F contract", () => {
    const wells = sampleWells();
    expect(wells).toHaveLength(96);
    for (const entry of wells) {
      const [column, row] = wellSortKey(entry.barcode);
      expect(`${String.fromCharCode(64 + row)}${column}`).toBe(entry.well);
    }
    expect(new Set(wells.map((entry) => entry.barcode)).size).toBe(96);
  });
});
