import { describe, expect, it } from "vitest";
import { nbLabel, nbOrderKey, wellSortKey } from "./nbLabel";

// Golden tables, kept in lockstep with tests/mame/test_nb_label.py, literal for
// literal. Editing one language alone breaks the other.
const NB_LABEL_CASES: ReadonlyArray<[string, string]> = [
  ["sort_barcode06", "NB06"],
  ["sort_barcode6", "NB6"],
  ["sort_barcode12", "NB12"],
  ["NB01", "NB01"],
  ["consensus", "consensus"],
  ["sorted_barcode09", "NB09"],
];

// [custom barcode, sequence index, well label] under the canonical addressing
// (reverse index is the row, origin A1, filling down each column).
//
// 2_5 against 5_2 is the row_axis discriminator: a diagonal token such as 3_3
// reads the same whichever half is the row. The seq column is the traversal
// discriminator: column-major and row-major both put 2_5 in B5 and only
// disagree about the index in between (34 against 17), so a table of well
// labels alone would pass under either.
const WELL_ADDRESS_CASES: ReadonlyArray<[string, number, string]> = [
  ["1_1", 1, "A1"],
  ["2_1", 2, "B1"],
  ["1_2", 9, "A2"],
  ["2_5", 34, "B5"],
  ["5_2", 13, "E2"],
  ["1_10", 73, "A10"],
  ["8_12", 96, "H12"],
];

// The canonical plate: 8 rows, 12 columns, filled down each column from A1.
// Mirrors kuma_core/mame/plate_geometry.DEFAULT_ADDRESSING.
const PLATE_ROWS = 8;

function seqToWell(seq: number): string {
  const rowIdx = (seq - 1) % PLATE_ROWS;
  const col = Math.floor((seq - 1) / PLATE_ROWS) + 1;
  return `${String.fromCharCode(65 + rowIdx)}${col}`;
}

describe("nbLabel", () => {
  it.each(NB_LABEL_CASES)("nbLabel(%j) === %j", (raw, expected) => {
    expect(nbLabel(raw)).toBe(expected);
  });
});

describe("nbOrderKey", () => {
  it("parses the first digit run", () => {
    expect(nbOrderKey("sort_barcode06")).toBe(6);
  });

  it("sorts non-numeric names last", () => {
    expect(nbOrderKey("consensus")).toBe(Number.MAX_SAFE_INTEGER);
  });
});

const byWell = (a: string, b: string) => {
  const ka = wellSortKey(a);
  const kb = wellSortKey(b);
  return ka[0] - kb[0] || ka[1] - kb[1];
};

describe("wellSortKey", () => {
  it("splits a {R}_{F} barcode into [F, R] (column, row)", () => {
    expect(wellSortKey("1_10")).toEqual([10, 1]);
    expect(wellSortKey("1_2")).toEqual([2, 1]);
  });

  it("orders naturally (1_2 before 1_10)", () => {
    expect(["1_10", "1_2"].sort(byWell)).toEqual(["1_2", "1_10"]);
  });

  it("is column-major: B1 (2_1) precedes A2 (1_2)", () => {
    // Off-diagonal discriminator, an all-same-R fixture cannot tell a
    // row-major (R, F) key from the column-major (F, R) one.
    expect(["1_2", "2_1", "1_1"].sort(byWell)).toEqual(["1_1", "2_1", "1_2"]);
  });

  it("reproduces seq_to_well order over a full plate", () => {
    // seq = (F - 1) * 8 + R  ->  A1, B1, ... H1, A2, ...
    const bySeq = Array.from(
      { length: 96 },
      (_, i) => `${(i % PLATE_ROWS) + 1}_${Math.floor(i / PLATE_ROWS) + 1}`,
    );
    expect([...bySeq].reverse().sort(byWell)).toEqual(bySeq);
    expect(bySeq.slice(0, 3)).toEqual(["1_1", "2_1", "3_1"]);
    expect(bySeq[8]).toBe("1_2");
    expect(seqToWell(1)).toBe("A1");
    expect(seqToWell(96)).toBe("H12");
  });
});

describe("well address golden table", () => {
  // The Python half is tests/mame/test_nb_label.py::test_well_address_golden_table,
  // asserting these same literals against DEFAULT_ADDRESSING. Changing the plate
  // convention on one side alone fails the other.
  it.each(WELL_ADDRESS_CASES)(
    "%s -> seq %i -> %s",
    (custom, seq, well) => {
      const [f, r] = wellSortKey(custom);
      expect((f - 1) * PLATE_ROWS + r).toBe(seq);
      expect(seqToWell(seq)).toBe(well);
    },
  );

  it("orders the table by its own seq column", () => {
    const sorted = [...WELL_ADDRESS_CASES]
      .map(([custom]) => custom)
      .sort(byWell);
    const bySeq = [...WELL_ADDRESS_CASES]
      .sort((a, b) => a[1] - b[1])
      .map(([custom]) => custom);
    expect(sorted).toEqual(bySeq);
  });
});
