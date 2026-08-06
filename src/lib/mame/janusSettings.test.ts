/**
 * loadJanusSettings: the two stored values that are promoted rather than merged.
 *
 * The panel used to offer a 5-column output sheet and used to ship a 100 uL
 * transfer volume it described as an assumption with no lab source. Neither is
 * offered any more: the instrument reads the 9-column sheet and the lab gave 70
 * uL for this run. A plain merge over the defaults would leave a machine that
 * ran an earlier build pinned to a value it now has no control to change, so
 * both are promoted on load.
 *
 * The line these tests hold is where the promotion stops. Any other stored
 * volume is an operator decision and must survive untouched, and the promotion
 * must never write on the shipped constant, which loadJanusSettings hands back
 * by reference when there is nothing stored.
 *
 * Tested directly rather than through the store: the mame input slice evaluates
 * loadJanusSettings() once at module load, so anything written to localStorage
 * after that import is invisible to it.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_JANUS_SETTINGS,
  JANUS_SETTINGS_STORAGE_KEY,
  loadJanusSettings,
  saveJanusSettings,
} from "./janusSettings";

/** Write a partial policy the way an earlier build would have left one behind. */
function storePolicy(value: unknown): void {
  localStorage.setItem(JANUS_SETTINGS_STORAGE_KEY, JSON.stringify(value));
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
});

describe("DEFAULT_JANUS_SETTINGS", () => {
  it("ships the volume this lab transfers", () => {
    // Pinned as a literal on purpose. scripts/sync-check-janus-defaults.mjs only
    // proves the TS and Python defaults agree with each other, so both sides
    // could move together and every gate would still be green.
    expect(DEFAULT_JANUS_SETTINGS.volume).toBe(70);
  });

  it("ships the 9-column instrument sheet", () => {
    expect(DEFAULT_JANUS_SETTINGS.outputSchema).toBe("device9");
  });
});

describe("loadJanusSettings", () => {
  it("returns the defaults when nothing was ever stored", () => {
    expect(loadJanusSettings()).toEqual(DEFAULT_JANUS_SETTINGS);
  });

  it("promotes a stored 100 uL, the old default, to the volume the lab gave", () => {
    // A stored 100 is the number the earlier build shipped and called an
    // assumption with no lab source, so it reads as never chosen. Left alone it
    // would keep writing 100 into the mapping file with no way to notice.
    storePolicy({ volume: 100 });

    expect(loadJanusSettings().volume).toBe(70);
  });

  it("leaves a volume the operator chose alone", () => {
    storePolicy({ volume: 55 });

    expect(loadJanusSettings().volume).toBe(55);
  });

  it("promotes only an exact 100, not a number near it", () => {
    // 100.5 could only have been typed, so it is a decision, not a leftover.
    storePolicy({ volume: 100.5 });

    expect(loadJanusSettings().volume).toBe(100.5);
  });

  it("leaves a stored volume that already matches the new default", () => {
    storePolicy({ volume: 70 });

    expect(loadJanusSettings().volume).toBe(70);
  });

  it("normalises the 5-column sheet to the instrument sheet", () => {
    // The panel dropped the schema choice, so a machine that picked the kuma
    // 5-column sheet before would otherwise keep exporting it with no control
    // left to switch back. The 5-column file is not lost: analyze still writes
    // the pick list in that shape on its own.
    storePolicy({ outputSchema: "legacy5" });

    expect(loadJanusSettings().outputSchema).toBe("device9");
  });

  it("leaves a stored instrument schema as it is", () => {
    storePolicy({ outputSchema: "device9" });

    expect(loadJanusSettings().outputSchema).toBe("device9");
  });

  it("promotes both values in one load", () => {
    storePolicy({ volume: 100, outputSchema: "legacy5" });

    const loaded = loadJanusSettings();

    expect(loaded.volume).toBe(70);
    expect(loaded.outputSchema).toBe("device9");
  });

  it("keeps the neighbouring stored fields while promoting", () => {
    storePolicy({ volume: 100, liquidClass: "Cell 100ul", destRack: 9 });

    const loaded = loadJanusSettings();

    expect(loaded.volume).toBe(70);
    expect(loaded.liquidClass).toBe("Cell 100ul");
    expect(loaded.destRack).toBe(9);
  });

  it("promotes on a copy, never on the shipped defaults", () => {
    storePolicy({ volume: 100, outputSchema: "legacy5" });

    loadJanusSettings();

    expect(DEFAULT_JANUS_SETTINGS.volume).toBe(70);
    expect(DEFAULT_JANUS_SETTINGS.outputSchema).toBe("device9");
    // The no-storage path hands the constant back by reference, so a migration
    // that wrote in place would poison every later read in the session. Checked
    // against the literals rather than against the constant, which would
    // compare a mutated object with itself and pass.
    localStorage.clear();
    const afterwards = loadJanusSettings();
    expect(afterwards.volume).toBe(70);
    expect(afterwards.outputSchema).toBe("device9");
  });

  it("falls back to the defaults for content it cannot read", () => {
    localStorage.setItem(JANUS_SETTINGS_STORAGE_KEY, "{ not json");
    expect(loadJanusSettings()).toEqual(DEFAULT_JANUS_SETTINGS);

    storePolicy(3);
    expect(loadJanusSettings()).toEqual(DEFAULT_JANUS_SETTINGS);

    storePolicy(null);
    expect(loadJanusSettings()).toEqual(DEFAULT_JANUS_SETTINGS);
  });

  it("reads back what saveJanusSettings wrote", () => {
    const chosen = {
      ...DEFAULT_JANUS_SETTINGS,
      volume: 55,
      liquidClass: "Cell 70ul",
      sourceRacks: { NB01: 2 },
    };

    saveJanusSettings(chosen);

    expect(loadJanusSettings()).toEqual(chosen);
  });
});
