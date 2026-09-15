/**
 * What a well read at its designed sites, as the verdict views show it.
 *
 * The sidecar reports `expected_site_reads` per verdict: one entry per designed
 * site whose `read` is the observed label at that position or one of three
 * tokens. An empty `observed_aa_changes` cannot tell those tokens apart (a well
 * that stayed WT and one with an N-bearing codon there both list nothing), so
 * the views name the token instead of printing a bare "-".
 *
 * A record without the field predates it (autosave replays verdicts verbatim)
 * and every helper here then returns exactly what the views showed before.
 */

import type { ExpectedSiteRead, VerdictRecord } from "@/types/mame/models";

/** `t` as the views pass it: a literal key in, a string out. */
export type Translate = (key: string) => string;

/** The three reads that are not an observed label. */
const SITE_READ_TOKENS: ReadonlySet<string> = new Set(["WT", "no call", "not covered"]);

export function isSiteReadToken(read: string): boolean {
  return SITE_READ_TOKENS.has(read);
}

/**
 * Display text for one read. The three tokens are translated; an observed label
 * ("L187A", "K48del") is shown verbatim.
 *
 * Each key is a literal `t()` call so scripts/i18n-lint.mjs resolves it.
 */
export function formatSiteRead(read: string, t: Translate): string {
  switch (read) {
    case "WT":
      return t("mame.verdictDetail.readWt");
    case "no call":
      return t("mame.verdictDetail.readNoCall");
    case "not covered":
      return t("mame.verdictDetail.readNotCovered");
    default:
      return read;
  }
}

/** The designed sites whose read is a token rather than an observed label. */
export function tokenSiteReads(
  record: Pick<VerdictRecord, "expected_site_reads">,
): ExpectedSiteRead[] {
  return (record.expected_site_reads ?? []).filter((site) => isSiteReadToken(site.read));
}

function sitePair(site: ExpectedSiteRead, t: Translate): string {
  return `${site.label}: ${formatSiteRead(site.read, t)}`;
}

/** "<label>: <formatted read>" for each site, joined with ", ". */
export function siteReadPairs(sites: readonly ExpectedSiteRead[], t: Translate): string {
  return sites.map((site) => sitePair(site, t)).join(", ");
}

/**
 * Text of the verdict table AA Changes cell, shared by its sort accessor and the
 * table search so all three agree.
 *
 * A WRONG_AA well carrying the field leads with its token sites, then the
 * observed labels: "L187G: WT", "L187G: no call", "L187A", "L187G: WT, A50T".
 * Every other record returns the observed labels joined, as before; an empty
 * result is left to the cell to render as "-".
 */
export function aaChangesText(
  record: Pick<VerdictRecord, "verdict" | "observed_aa_changes" | "expected_site_reads">,
  t: Translate,
): string {
  const observed = record.observed_aa_changes;
  if (record.verdict !== "WRONG_AA" || record.expected_site_reads === undefined) {
    return observed.join(", ");
  }
  const tokens = tokenSiteReads(record).map((site) => sitePair(site, t));
  return [...tokens, ...observed].join(", ");
}
