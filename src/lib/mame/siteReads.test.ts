import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import type { ExpectedSiteRead, VerdictRecord } from "@/types/mame/models";
import {
  aaChangesText,
  formatSiteRead,
  isSiteReadToken,
  siteReadPairs,
  tokenSiteReads,
} from "./siteReads";

const EN = en.mame.verdictDetail;

/** Resolves against en.json, and returns the key itself when it is not there. */
function t(key: string): string {
  const leaf = key.replace(/^mame\.verdictDetail\./, "");
  const value = (EN as Record<string, unknown>)[leaf];
  return typeof value === "string" ? value : key;
}

type Row = Pick<VerdictRecord, "verdict" | "observed_aa_changes" | "expected_site_reads">;

function site(label: string, position: number, read: string): ExpectedSiteRead {
  return { label, position, read };
}

describe("formatSiteRead", () => {
  it("maps each token to its own locale key", () => {
    const keyOnly = (key: string) => `<${key}>`;
    expect(formatSiteRead("WT", keyOnly)).toBe("<mame.verdictDetail.readWt>");
    expect(formatSiteRead("no call", keyOnly)).toBe("<mame.verdictDetail.readNoCall>");
    expect(formatSiteRead("not covered", keyOnly)).toBe("<mame.verdictDetail.readNotCovered>");
  });

  it("renders the en values for the tokens", () => {
    expect(formatSiteRead("WT", t)).toBe(EN.readWt);
    expect(formatSiteRead("no call", t)).toBe(EN.readNoCall);
    expect(formatSiteRead("not covered", t)).toBe(EN.readNotCovered);
  });

  it("shows an observed label verbatim", () => {
    const keyOnly = (key: string) => `<${key}>`;
    expect(formatSiteRead("L187A", keyOnly)).toBe("L187A");
    expect(formatSiteRead("K48del", keyOnly)).toBe("K48del");
    // Tokens are exact strings: a label that merely contains one is a label.
    expect(formatSiteRead("WT1", keyOnly)).toBe("WT1");
  });
});

describe("tokenSiteReads", () => {
  it("keeps only the sites whose read is a token", () => {
    const sites = [
      site("L187G", 187, "WT"),
      site("A50T", 50, "A50T"),
      site("K48A", 48, "no call"),
      site("R9K", 9, "not covered"),
    ];
    expect(tokenSiteReads({ expected_site_reads: sites }).map((s) => s.label)).toEqual([
      "L187G",
      "K48A",
      "R9K",
    ]);
    expect(isSiteReadToken("A50T")).toBe(false);
  });

  it("returns nothing for a record that predates the field", () => {
    expect(tokenSiteReads({})).toEqual([]);
  });
});

describe("siteReadPairs", () => {
  it("joins label and formatted read per site", () => {
    expect(siteReadPairs([site("L187G", 187, "WT"), site("K48A", 48, "L187A")], t)).toBe(
      "L187G: WT, K48A: L187A",
    );
  });
});

describe("aaChangesText", () => {
  it("names a WRONG_AA site that stayed WT", () => {
    const row: Row = {
      verdict: "WRONG_AA",
      observed_aa_changes: [],
      expected_site_reads: [site("L187G", 187, "WT")],
    };
    expect(aaChangesText(row, t)).toBe("L187G: WT");
  });

  it("names a WRONG_AA site with no call", () => {
    const row: Row = {
      verdict: "WRONG_AA",
      observed_aa_changes: [],
      expected_site_reads: [site("L187G", 187, "no call")],
    };
    expect(aaChangesText(row, t)).toBe("L187G: no call");
  });

  it("keeps a wrong residue as the observed label alone", () => {
    const row: Row = {
      verdict: "WRONG_AA",
      observed_aa_changes: ["L187A"],
      expected_site_reads: [site("L187G", 187, "L187A")],
    };
    expect(aaChangesText(row, t)).toBe("L187A");
  });

  it("puts the token sites ahead of an extra observed change", () => {
    const row: Row = {
      verdict: "WRONG_AA",
      observed_aa_changes: ["A50T"],
      expected_site_reads: [site("L187G", 187, "WT")],
    };
    expect(aaChangesText(row, t)).toBe("L187G: WT, A50T");
  });

  it("leaves a record without the field exactly as before", () => {
    expect(aaChangesText({ verdict: "WRONG_AA", observed_aa_changes: [] }, t)).toBe("");
    expect(
      aaChangesText({ verdict: "WRONG_AA", observed_aa_changes: ["V5S", "A1G"] }, t),
    ).toBe("V5S, A1G");
  });

  it("leaves every other verdict class as before even with the field", () => {
    const row: Row = {
      verdict: "NO_CALL",
      observed_aa_changes: [],
      expected_site_reads: [site("L187G", 187, "no call")],
    };
    expect(aaChangesText(row, t)).toBe("");
    expect(
      aaChangesText(
        { verdict: "PASS", observed_aa_changes: ["F89W"], expected_site_reads: [site("F89W", 89, "F89W")] },
        t,
      ),
    ).toBe("F89W");
  });
});
