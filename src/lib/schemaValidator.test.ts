import { describe, expect, it } from "vitest";
import { extractCsvHeader, MAME_ACTIVITY_CSV_SCHEMA, validateCsvHeader } from "./schemaValidator";

describe("CSV header records", () => {
  it.each([
    '"well_id","value"\r\nA1,3',
    '\uFEFF"well_id","value"\nA1,3',
    'well_id,value\nA1,3',
    '"Sample Name","Area"\nA1,3',
  ])("FL-04: accepts valid activity headers from %j", (csv) => {
    const result = validateCsvHeader(extractCsvHeader(csv), MAME_ACTIVITY_CSV_SCHEMA);
    expect(result.valid).toBe(true);
    expect(result.missing).toEqual([]);
  });

  it.each([
    ['"well_id","value","note, detail"\nA1,3,x', undefined, ["well_id", "value", "note, detail"]],
    ['"well_id","value","a ""quote"""\nA1,3,x', undefined, ["well_id", "value", 'a "quote"']],
    ['"well_id","value","two\nlines"\r\nA1,3,x', undefined, ["well_id", "value", "two\nlines"]],
    ['"well_id"\t"value"\t"note\tdetail"\nA1\t3\tx', "tsv", ["well_id", "value", "note\tdetail"]],
    ["well_id,value,\rA1,3,x", undefined, ["well_id", "value", ""]],
    ["", undefined, [""]],
  ] satisfies [string, string | undefined, string[]][]) (
    "FL-04: parses only the first record of %j", (csv, ext, expected) => {
      expect(extractCsvHeader(csv, ext)).toEqual(expected);
    },
  );
});
