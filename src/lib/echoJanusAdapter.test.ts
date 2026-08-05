import { describe, it, expect } from "vitest";
import {
  adaptEchoRows,
  adaptJanusRows,
  adaptDestCellsJanus,
  type JanusDryRunRow,
} from "./echoJanusAdapter";

/** A Janus dry-run row with every field set; specs override what they exercise. */
function janusRow(over: Partial<JanusDryRunRow> = {}): JanusDryRunRow {
  return {
    name: "M1A-F",
    type: "primer",
    dsp_rack_label: "Oligo 5pmol/ul",
    no: 1,
    asp_rack: 1,
    asp_posi: "A1",
    dsp_rack: 3,
    dsp_posi: "A1",
    volume: 2.0,
    mutation: "M1A",
    ...over,
  };
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
  // Fallback path: rows without `role` (a sidecar built before the field
  // existed) still split on the KURO default deck numbers.
  it("splits rack 1 (asp_rack=1) and rack 2 (asp_rack=2) by asp_rack value", () => {
    const { rack1, rack2 } = adaptJanusRows([
      {
        name: "P1-fw",
        type: "primer",
        dsp_rack_label: "x",
        no: 1,
        asp_rack: 1,
        asp_posi: "A1",
        dsp_rack: 3,
        dsp_posi: "A1",
        volume: 2.0,
      mutation: "M",
      },
      {
        name: "P1-rv",
        type: "primer",
        dsp_rack_label: "x",
        no: 2,
        asp_rack: 2,
        asp_posi: "B2",
        dsp_rack: 3,
        dsp_posi: "A1",
        volume: 2.0,
      mutation: "M",
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

  it("skips rows with asp_rack outside {1,2}", () => {
    const { rack1, rack2 } = adaptJanusRows([
      {
        name: "stray",
        type: "primer",
        dsp_rack_label: "x",
        no: 3,
        asp_rack: 0,
        asp_posi: "A1",
        dsp_rack: 3,
        dsp_posi: "A1",
        volume: 2.0,
      mutation: "M",
      },
      {
        name: "stray2",
        type: "primer",
        dsp_rack_label: "x",
        no: 4,
        asp_rack: 5,
        asp_posi: "B2",
        dsp_rack: 3,
        dsp_posi: "A1",
        volume: 2.0,
      mutation: "M",
      },
    ]);
    expect(rack1).toHaveLength(0);
    expect(rack2).toHaveLength(0);
  });

  it("boundary H12 row=H col=12 in rack 2 when asp_rack=2", () => {
    const { rack1, rack2 } = adaptJanusRows([
      {
        name: "last",
        type: "primer",
        dsp_rack_label: "x",
        no: 96,
        asp_rack: 2,
        asp_posi: "H12",
        dsp_rack: 3,
        dsp_posi: "H12",
        volume: 1.5,
      mutation: "M",
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

  it("uses role when present, ignoring the rack number", () => {
    const { rack1, rack2 } = adaptJanusRows([
      janusRow({ name: "M1A-F", role: "fwd", asp_rack: 2, asp_posi: "A1" }),
      janusRow({ name: "M1A-R", role: "rev", asp_rack: 1, asp_posi: "B2" }),
    ]);
    expect(rack1.map((c) => c.name)).toEqual(["M1A-F"]);
    expect(rack2.map((c) => c.name)).toEqual(["M1A-R"]);
  });

  // Regression: the whole point of the `role` field. A lab that renumbers the
  // deck (KURO_PRIMER_DECK fwd_rack/rev_rack no longer 1/2) used to have F and
  // R silently swapped or dropped, because direction was read off the rack.
  it("keeps direction on a non-standard deck (fwd=5, rev=6)", () => {
    const { rack1, rack2 } = adaptJanusRows([
      janusRow({ name: "M1A-F", role: "fwd", asp_rack: 5, asp_posi: "C3" }),
      janusRow({ name: "M1A-R", role: "rev", asp_rack: 6, asp_posi: "D4" }),
    ]);
    expect(rack1).toHaveLength(1);
    expect(rack2).toHaveLength(1);
    expect(rack1[0]).toMatchObject({ name: "M1A-F", well: "C3", rack: 1 });
    expect(rack2[0]).toMatchObject({ name: "M1A-R", well: "D4", rack: 2 });
  });

  it("skips a row with neither role nor a known deck rack", () => {
    const { rack1, rack2 } = adaptJanusRows([
      janusRow({ asp_rack: 5, asp_posi: "C3" }),
    ]);
    expect(rack1).toHaveLength(0);
    expect(rack2).toHaveLength(0);
  });
});

describe("adaptDestCellsJanus", () => {
  it("falls back to the deck rack numbers when role is absent", () => {
    const [cell] = adaptDestCellsJanus([
      janusRow({ asp_rack: 1, asp_posi: "A1", dsp_posi: "A1", volume: 2 }),
      janusRow({ asp_rack: 2, asp_posi: "B2", dsp_posi: "A1", volume: 3 }),
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

  it("keeps F/R on a non-standard deck when role is present", () => {
    const [cell] = adaptDestCellsJanus([
      janusRow({ role: "fwd", asp_rack: 5, asp_posi: "C3", volume: 2 }),
      janusRow({ role: "rev", asp_rack: 6, asp_posi: "D4", volume: 3 }),
    ]);
    expect(cell).toMatchObject({
      hasF: true,
      hasR: true,
      fwdSource: "C3",
      revSource: "D4",
    });
  });

  it("skips a row whose direction cannot be established", () => {
    expect(adaptDestCellsJanus([janusRow({ asp_rack: 7 })])).toEqual([]);
  });
});
