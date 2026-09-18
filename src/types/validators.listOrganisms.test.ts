/**
 * `list_organisms` envelope guard (`isListOrganismsResult`, reached through the
 * RPC validator table).
 *
 * The guard is the only thing standing between a hand-written codon table on
 * disk and the organism dropdown. Two failure modes are worth pinning:
 *
 *  1. The shape moved. `list_organisms` used to answer with a bare array and
 *     now answers with `{organisms, failed, user_dir}`; a sidecar built before
 *     that change must be rejected rather than silently yielding an undefined
 *     `organisms`.
 *  2. The nullable fields must stay nullable. `taxid` and `cds_count` are
 *     `data.get(...)` on the backend and a hand-written table declares neither
 *     (kuma_core/kuro/codon_table.py, `CodonTableRegistry.scan`). Requiring a
 *     number there made one taxid-less user table reject the whole payload and
 *     render an empty dropdown, which is the regression the guard comment in
 *     validators.ts describes.
 *
 * The fixtures carry all eight organism keys because `scan()` always emits all
 * eight: `aliases` is `list(report.aliases)` and `table_sha256` is
 * `report.table_sha256`, which is a `str` on every `report.ok` path
 * (kuma_core/kuro/codon_import.py, the `if report.ok and normalised is not
 * None` block).
 */

import { describe, expect, it } from "vitest";
import { getRpcResultValidator } from "@/types/validators";

const validate = getRpcResultValidator("list_organisms");

/** A bundled table exactly as `handle_list_organisms` reports one. */
function builtin(): Record<string, unknown> {
  return {
    key: "ecoli",
    name: "Escherichia coli K-12",
    taxid: 511145,
    source: "builtin",
    aliases: ["e_coli", "escherichia coli"],
    cds_count: 14,
    table_sha256: "a".repeat(64),
    warnings: [],
  };
}

/** The seeded user table, which declares neither taxid nor a CDS count. */
function userTable(): Record<string, unknown> {
  return {
    key: "example_strain",
    name: "Example strain (rename me)",
    taxid: null,
    source: "user",
    aliases: [],
    cds_count: null,
    table_sha256: "b".repeat(64),
    warnings: [{ code: "V32", params: {} }],
  };
}

function envelope(over: Record<string, unknown> = {}): unknown {
  return {
    organisms: [builtin(), userTable()],
    failed: [],
    user_dir: "/home/u/.local/share/kuma/codon_tables",
    ...over,
  };
}

describe("list_organisms envelope: accepted payloads", () => {
  it("CONTROL accepts the real two-entry envelope", () => {
    expect(validate(envelope())).toBe(true);
  });

  it("accepts an empty listing (no tables found, folder still resolved)", () => {
    expect(validate({ organisms: [], failed: [], user_dir: "" })).toBe(true);
  });

  it("accepts a taxid-less, cds_count-less user table on its own", () => {
    expect(validate(envelope({ organisms: [userTable()] }))).toBe(true);
  });

  it("accepts a populated failed[] alongside loaded organisms", () => {
    // The R5 shadowing row, verbatim from CodonTableRegistry.scan.
    expect(
      validate(
        envelope({
          failed: [
            {
              filename: "ecoli.json",
              code: "R5",
              reason:
                "ecoli.json is shadowed by the built-in table 'ecoli' and was "
                + "not loaded. Rename it to ecoli_lab.json to use it.",
            },
            { filename: "broken.json", code: "V17", reason: "Expected 21 amino acid entries." },
          ],
        }),
      ),
    ).toBe(true);
  });

  it("accepts warnings carrying interpolation params", () => {
    const withWarnings = {
      ...userTable(),
      warnings: [
        { code: "V31", params: { cds: 3, codons: 900 } },
        { code: "V33", params: { name: "Example strain" } },
      ],
    };
    expect(validate(envelope({ organisms: [withWarnings] }))).toBe(true);
  });

  it("accepts extra top-level keys, so the backend may widen the envelope", () => {
    expect(validate(envelope({ builtin_dir: "/opt/kuma/codon_tables" }))).toBe(true);
  });
});

describe("list_organisms envelope: rejected payloads", () => {
  it("rejects the pre-change bare array", () => {
    expect(validate([builtin(), userTable()])).toBe(false);
    expect(validate([])).toBe(false);
  });

  it.each([
    ["organisms missing", { organisms: undefined }],
    ["organisms null", { organisms: null }],
    ["organisms an object", { organisms: { ecoli: builtin() } }],
    ["failed not an array", { failed: {} }],
    ["failed null", { failed: null }],
    ["user_dir missing", { user_dir: undefined }],
    ["user_dir null", { user_dir: null }],
    ["user_dir a number", { user_dir: 0 }],
  ])("rejects an envelope with %s", (_label, over) => {
    expect(validate(envelope(over))).toBe(false);
  });

  it.each([null, undefined, 42, "organisms", true])("rejects non-object %j", (value) => {
    expect(validate(value)).toBe(false);
  });

  it.each([
    ["key missing", { key: undefined }],
    ["key a number", { key: 1 }],
    ["name null", { name: null }],
    ["taxid a numeric string", { taxid: "511145" }],
    ["taxid NaN", { taxid: Number.NaN }],
    ["cds_count a string", { cds_count: "14" }],
    ["aliases a bare string", { aliases: "e_coli" }],
    ["aliases holding a non-string", { aliases: ["e_coli", 7] }],
    ["aliases missing", { aliases: undefined }],
    ["table_sha256 null", { table_sha256: null }],
    ["table_sha256 missing", { table_sha256: undefined }],
    ["warnings missing", { warnings: undefined }],
    ["warnings an object", { warnings: {} }],
  ])("rejects an organism with %s", (_label, over) => {
    expect(validate(envelope({ organisms: [{ ...builtin(), ...over }] }))).toBe(false);
  });

  // Substring traps: `source` is an exact two-value union, not a prefix test.
  it.each(["Builtin", "built-in", "builtins", "builtin ", "user_table", "User", "", "system"])(
    "rejects source %j",
    (source) => {
      expect(validate(envelope({ organisms: [{ ...builtin(), source }] }))).toBe(false);
    },
  );

  it.each([
    ["params missing", { code: "V32" }],
    ["params an array", { code: "V32", params: [] }],
    ["params null", { code: "V32", params: null }],
    ["code missing", { params: {} }],
    ["code a number", { code: 32, params: {} }],
    ["a bare code string", "V32"],
    ["null", null],
  ])("rejects a warning with %s", (_label, warning) => {
    expect(validate(envelope({ organisms: [{ ...builtin(), warnings: [warning] }] }))).toBe(false);
  });

  it.each([
    ["filename missing", { code: "R5", reason: "x" }],
    ["code missing", { filename: "a.json", reason: "x" }],
    ["reason missing", { filename: "a.json", code: "R5" }],
    ["reason a number", { filename: "a.json", code: "R5", reason: 5 }],
    ["a bare filename string", "a.json"],
    ["null", null],
  ])("rejects a failed entry with %s", (_label, failure) => {
    expect(validate(envelope({ failed: [failure] }))).toBe(false);
  });

  // The documented blast radius: element guards run per element, so one bad
  // row rejects the listing rather than being dropped from it.
  it("rejects the whole envelope when a single organism among good ones is malformed", () => {
    expect(
      validate(envelope({ organisms: [builtin(), { ...userTable(), source: "usr" }, builtin()] })),
    ).toBe(false);
  });
});
