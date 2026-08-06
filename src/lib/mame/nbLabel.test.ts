import { describe, expect, it } from "vitest";
import { nbLabel, nbOrderKey, wellSortKey } from "./nbLabel";

// Golden table — kept in lockstep with tests/mame/test_nb_label.py.
const NB_LABEL_CASES: ReadonlyArray<[string, string]> = [
  ["sort_barcode06", "NB06"],
  ["sort_barcode6", "NB6"],
  ["sort_barcode12", "NB12"],
  ["NB01", "NB01"],
  ["consensus", "consensus"],
  ["sorted_barcode09", "NB09"],
];

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
    // seq = (F - 1) * 8 + R  →  A1, B1, ... H1, A2, ...
    const bySeq = Array.from(
      { length: 96 },
      (_, i) => `${(i % 8) + 1}_${Math.floor(i / 8) + 1}`,
    );
    expect([...bySeq].reverse().sort(byWell)).toEqual(bySeq);
    expect(bySeq.slice(0, 3)).toEqual(["1_1", "2_1", "3_1"]);
    expect(bySeq[8]).toBe("1_2");
  });
});
