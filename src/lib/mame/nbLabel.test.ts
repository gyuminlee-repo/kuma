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

describe("wellSortKey", () => {
  it("splits a {R}_{F} barcode into numeric parts", () => {
    expect(wellSortKey("1_10")).toEqual([1, 10]);
    expect(wellSortKey("1_2")).toEqual([1, 2]);
  });

  it("orders naturally (1_2 before 1_10)", () => {
    const sorted = ["1_10", "1_2"].sort((a, b) => {
      const ka = wellSortKey(a);
      const kb = wellSortKey(b);
      return ka[0] - kb[0] || ka[1] - kb[1];
    });
    expect(sorted).toEqual(["1_2", "1_10"]);
  });
});
