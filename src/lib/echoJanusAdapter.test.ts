import { describe, it, expect } from "vitest";
import {
  adaptEchoRows,
  adaptJanusRows,
  adaptDestCellsJanus,
  type JanusDryRunRow,
} from "./echoJanusAdapter";

/**
 * A Janus dry-run row with every field set; specs override what they exercise.
 * Rack fields hold plate names, matching `KURO_PRIMER_DECK`
 * (kuma_core/shared/janus_deck.py) as `build_janus_rows` writes them.
 */
function janusRow(over: Partial<JanusDryRunRow> = {}): JanusDryRunRow {
  return {
    name: "M1A-F",
    type: "primer",
    no: 1,
    asp_rack: "fw plate",
    asp_posi: "A1",
    dsp_rack: "PCR mixture plate",
    dsp_posi: "A1",
    volume: 2.0,
    mutation: "M1A",
    role: "fwd",
    ...over,
  };
}

/** The same row as a payload that never stated a direction. */
function janusRowWithoutRole(over: Partial<JanusDryRunRow> = {}): JanusDryRunRow {
  const row = janusRow(over);
  delete row.role;
  return row;
}

describe("adaptEchoRows", () => {
  it("parses 384-well coord A01 row=A col=1 isFwd=true", () => {
    const cells = adaptEchoRows([
      {
        source_plate: "Source [1]",
        source_well_name: "P1-fw",
        source_well: "A01",
        dest_plate: "Dest [1]",
        dest_well_name: "P1",
        dest_well: "A1",
        transfer_vol: 100,
      mutation: "M",
      },
    ]);
    expect(cells[0]).toMatchObject({
      well: "A01",
      rowLetter: "A",
      colNumber: 1,
      isFwd: true,
      sourceWellName: "P1-fw",
      destPlate: "Dest [1]",
      destWell: "A1",
      transferVolNl: 100,
    });
  });

  it("normalizes backend well A1 to grid key A01", () => {
    const cells = adaptEchoRows([
      {
        source_plate: "Source [1]",
        source_well_name: "P1-fw",
        source_well: "A1",
        dest_plate: "Dest [1]",
        dest_well_name: "P1",
        dest_well: "A1",
        transfer_vol: 100,
      mutation: "M",
      },
    ]);
    expect(cells[0]).toMatchObject({
      well: "A01",
      rowLetter: "A",
      colNumber: 1,
      isFwd: true,
    });
  });

  it("rev row B even = isFwd=false", () => {
    const cells = adaptEchoRows([
      {
        source_well: "B03",
        source_well_name: "x",
        source_plate: "",
        dest_plate: "",
        dest_well_name: "",
        dest_well: "",
        transfer_vol: 50,
      mutation: "M",
      },
    ]);
    expect(cells[0].isFwd).toBe(false);
    expect(cells[0].rowLetter).toBe("B");
    expect(cells[0].colNumber).toBe(3);
  });

  it("boundary P24 row=P col=24 isFwd=false (P is 16th row, idx 15, odd)", () => {
    const cells = adaptEchoRows([
      {
        source_well: "P24",
        source_well_name: "last",
        source_plate: "",
        dest_plate: "",
        dest_well_name: "",
        dest_well: "",
        transfer_vol: 25,
      mutation: "M",
      },
    ]);
    expect(cells[0]).toMatchObject({
      well: "P24",
      rowLetter: "P",
      colNumber: 24,
      isFwd: false,
    });
  });
});

describe("adaptJanusRows", () => {
  it("splits fwd rows into panel 1 and rev rows into panel 2", () => {
    const { rack1, rack2 } = adaptJanusRows([
      {
        name: "P1-fw",
        type: "primer",
        no: 1,
        asp_rack: "fw plate",
        asp_posi: "A1",
        dsp_rack: "PCR mixture plate",
        dsp_posi: "A1",
        volume: 2.0,
        mutation: "M",
        role: "fwd",
      },
      {
        name: "P1-rv",
        type: "primer",
        no: 2,
        asp_rack: "rv plate",
        asp_posi: "B2",
        dsp_rack: "PCR mixture plate",
        dsp_posi: "A1",
        volume: 2.0,
        mutation: "M",
        role: "rev",
      },
    ]);
    expect(rack1).toHaveLength(1);
    expect(rack2).toHaveLength(1);
    expect(rack1[0]).toMatchObject({
      rack: 1,
      well: "A1",
      rowLetter: "A",
      colNumber: 1,
      name: "P1-fw",
      volumeUl: 2.0,
    });
    expect(rack2[0]).toMatchObject({
      rack: 2,
      well: "B2",
      rowLetter: "B",
      colNumber: 2,
      name: "P1-rv",
      volumeUl: 2.0,
    });
  });

  it("boundary H12 row=H col=12 in panel 2 for a rev row", () => {
    const { rack1, rack2 } = adaptJanusRows([
      {
        name: "last",
        type: "primer",
        no: 96,
        asp_rack: "rv plate",
        asp_posi: "H12",
        dsp_rack: "PCR mixture plate",
        dsp_posi: "H12",
        volume: 1.5,
        mutation: "M",
        role: "rev",
      },
    ]);
    expect(rack1).toHaveLength(0);
    expect(rack2[0]).toMatchObject({
      rack: 2,
      well: "H12",
      rowLetter: "H",
      colNumber: 12,
    });
  });

  it("uses role, not the plate names, even when the two are swapped", () => {
    const { rack1, rack2 } = adaptJanusRows([
      janusRow({ name: "M1A-F", role: "fwd", asp_rack: "rv plate", asp_posi: "A1" }),
      janusRow({ name: "M1A-R", role: "rev", asp_rack: "fw plate", asp_posi: "B2" }),
    ]);
    expect(rack1.map((c) => c.name)).toEqual(["M1A-F"]);
    expect(rack2.map((c) => c.name)).toEqual(["M1A-R"]);
  });

  // Regression: the whole point of the `role` field. A lab that relabels the
  // deck used to have F and R silently swapped or dropped, because direction
  // was read off the rack.
  it("keeps direction when the deck plates are renamed", () => {
    const { rack1, rack2 } = adaptJanusRows([
      janusRow({ name: "M1A-F", role: "fwd", asp_rack: "Stock plate1", asp_posi: "C3" }),
      janusRow({ name: "M1A-R", role: "rev", asp_rack: "Stock plate2", asp_posi: "D4" }),
    ]);
    expect(rack1).toHaveLength(1);
    expect(rack2).toHaveLength(1);
    expect(rack1[0]).toMatchObject({ name: "M1A-F", well: "C3", rack: 1 });
    expect(rack2[0]).toMatchObject({ name: "M1A-R", well: "D4", rack: 2 });
  });

  // Pins the removal of the old rack-number fallback: a row on the KURO
  // default deck used to be adopted as forward on the strength of its rack
  // alone. Direction is now stated or the row does not render.
  it("skips a row that does not state its role, even on the default deck", () => {
    const { rack1, rack2 } = adaptJanusRows([
      janusRowWithoutRole({ asp_rack: "fw plate", asp_posi: "A1" }),
      janusRowWithoutRole({ asp_rack: "rv plate", asp_posi: "B2" }),
    ]);
    expect(rack1).toHaveLength(0);
    expect(rack2).toHaveLength(0);
  });
});

describe("adaptDestCellsJanus", () => {
  it("pairs the F and R rows of one mutation into a single dest cell", () => {
    const [cell] = adaptDestCellsJanus([
      janusRow({ role: "fwd", asp_rack: "fw plate", asp_posi: "A1", dsp_posi: "A1", volume: 2 }),
      janusRow({ role: "rev", asp_rack: "rv plate", asp_posi: "B2", dsp_posi: "A1", volume: 3 }),
    ]);
    expect(cell).toMatchObject({
      mutation: "M1A",
      hasF: true,
      hasR: true,
      fwdVol: 2,
      revVol: 3,
      fwdSource: "A1",
      revSource: "B2",
    });
  });

  it("keeps F/R when the deck plates are renamed", () => {
    const [cell] = adaptDestCellsJanus([
      janusRow({ role: "fwd", asp_rack: "Stock plate1", asp_posi: "C3", volume: 2 }),
      janusRow({ role: "rev", asp_rack: "Stock plate2", asp_posi: "D4", volume: 3 }),
    ]);
    expect(cell).toMatchObject({
      hasF: true,
      hasR: true,
      fwdSource: "C3",
      revSource: "D4",
    });
  });

  it("skips a row that does not state its role", () => {
    expect(adaptDestCellsJanus([janusRowWithoutRole()])).toEqual([]);
  });
});
