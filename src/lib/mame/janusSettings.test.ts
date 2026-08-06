/**
 * loadJanusSettings: the stored values that are promoted rather than merged.
 *
 * A machine that ran an earlier build has a policy in localStorage, and a plain
 * merge over the defaults lets that policy win. Where the panel has since
 * dropped the control that set a value, winning means being pinned to something
 * with no way left to change it, so those values are promoted on load:
 *
 *  - a 100 uL volume, shipped by a build that called it an assumption with no
 *    lab source, where the lab has since given 70 uL
 *  - the 5-column output sheet, which the panel no longer offers
 *  - "device9", the instrument schema named for a sheet that had nine columns,
 *    where the lab has since replaced it with an eight column one
 *  - a "cell" sample type, where the seeding workbook writes "cell stock"
 *  - rack NUMBERS, from when the panel asked for them, where the two rack
 *    columns now carry plate names the sidecar generates
 *
 * The line these tests hold is where the promotion stops. Any other stored
 * volume is an operator decision and must survive untouched, a stored plate
 * name is an override the sidecar still honours, and the promotion must never
 * write on the shipped constant, which loadJanusSettings hands back by
 * reference when there is nothing stored.
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

  it("ships the instrument sheet", () => {
    expect(DEFAULT_JANUS_SETTINGS.outputSchema).toBe("device");
  });

  it("ships the type value the seeding workbook writes", () => {
    // Every row of the lab workbook reads "cell stock" in this column, and the
    // sync-check only proves the two sides agree with each other, so the
    // literal is pinned here against the workbook rather than against Python.
    expect(DEFAULT_JANUS_SETTINGS.sampleType).toBe("cell stock");
  });

  it("names no plate, leaving the sidecar to generate every name", () => {
    expect(DEFAULT_JANUS_SETTINGS.sourceRacks).toEqual({});
    expect(DEFAULT_JANUS_SETTINGS.destRack).toBeNull();
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

    expect(loadJanusSettings().outputSchema).toBe("device");
  });

  it("leaves a stored instrument schema as it is", () => {
    storePolicy({ outputSchema: "device" });

    expect(loadJanusSettings().outputSchema).toBe("device");
  });

  it("renames a stored device9 to the schema that lost the column count", () => {
    // The instrument schema was called "device9" while its sheet had nine
    // columns. The lab replaced that sheet with an eight column one, so the
    // count left the name. The sidecar validates the schema against a fixed
    // list and the old string is not on it, so a machine that kept sending it
    // would have every export refused rather than degraded.
    storePolicy({ outputSchema: "device9" });

    expect(loadJanusSettings().outputSchema).toBe("device");
  });

  it("drops stored rack numbers, restoring the generated plate names", () => {
    // The panel used to ask for rack NUMBERS and the two rack columns carry
    // plate names now. A stored 1 is not a name that can be repaired into
    // "Stock plate1": as an override it would put a bare number where the robot
    // expects a labware name, and no field is left to correct it in.
    storePolicy({ sourceRacks: { NB01: 1, NB02: 2 }, destRack: 3 });

    const loaded = loadJanusSettings();

    expect(loaded.sourceRacks).toEqual({});
    expect(loaded.destRack).toBeNull();
  });

  it("keeps a stored plate name, which is an override the sidecar honours", () => {
    storePolicy({
      sourceRacks: { NB01: "Stock plate4" },
      destRack: "spare culture plate",
    });

    const loaded = loadJanusSettings();

    expect(loaded.sourceRacks).toEqual({ NB01: "Stock plate4" });
    expect(loaded.destRack).toBe("spare culture plate");
  });

  it("discards a half-named deck whole rather than keeping the named half", () => {
    // Half names and half numbers describes no run, and keeping the readable
    // half would ship a file naming one plate and numbering the next.
    storePolicy({ sourceRacks: { NB01: "Stock plate1", NB02: 2 } });

    expect(loadJanusSettings().sourceRacks).toEqual({});
  });

  it("promotes a stored device9 and its rack numbers in one load", () => {
    // The state an actual machine is in: both were written by the same build.
    storePolicy({
      outputSchema: "device9",
      sourceRacks: { NB01: 1, NB02: 2 },
      destRack: 3,
      sampleType: "cell",
      volume: 100,
    });

    const loaded = loadJanusSettings();

    expect(loaded.outputSchema).toBe("device");
    expect(loaded.sourceRacks).toEqual({});
    expect(loaded.destRack).toBeNull();
    expect(loaded.sampleType).toBe("cell stock");
    expect(loaded.volume).toBe(70);
  });

  it("promotes the shipped type value but not one the operator typed", () => {
    storePolicy({ sampleType: "cell" });
    expect(loadJanusSettings().sampleType).toBe("cell stock");

    // An operator saying what the plate holds is stating something the shipped
    // default cannot know, so it survives.
    storePolicy({ sampleType: "glycerol stock" });
    expect(loadJanusSettings().sampleType).toBe("glycerol stock");
  });

  it("keeps the neighbouring stored fields while promoting", () => {
    storePolicy({
      volume: 100,
      liquidClass: "Cell 100ul",
      destRack: "final culture plate",
    });

    const loaded = loadJanusSettings();

    expect(loaded.volume).toBe(70);
    // Recorded with the run and written to no file, so nothing may quietly drop
    // it either.
    expect(loaded.liquidClass).toBe("Cell 100ul");
    expect(loaded.destRack).toBe("final culture plate");
  });

  it("promotes on a copy, never on the shipped defaults", () => {
    storePolicy({ volume: 100, outputSchema: "legacy5", sourceRacks: { NB01: 1 } });

    loadJanusSettings();

    expect(DEFAULT_JANUS_SETTINGS.volume).toBe(70);
    expect(DEFAULT_JANUS_SETTINGS.outputSchema).toBe("device");
    expect(DEFAULT_JANUS_SETTINGS.sourceRacks).toEqual({});
    // The no-storage path hands the constant back by reference, so a migration
    // that wrote in place would poison every later read in the session. Checked
    // against the literals rather than against the constant, which would
    // compare a mutated object with itself and pass.
    localStorage.clear();
    const afterwards = loadJanusSettings();
    expect(afterwards.volume).toBe(70);
    expect(afterwards.outputSchema).toBe("device");
    expect(afterwards.sourceRacks).toEqual({});
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
      sourceRacks: { NB01: "Stock plate2" },
    };

    saveJanusSettings(chosen);

    expect(loadJanusSettings()).toEqual(chosen);
  });
});
