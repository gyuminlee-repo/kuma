import { describe, it, expect } from "vitest";
import { adaptEchoRows, adaptJanusRows } from "./echoJanusAdapter";

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
});
