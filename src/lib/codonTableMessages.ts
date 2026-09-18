/**
 * Codon-table validator message codes -> localized sentences.
 *
 * The sidecar reports a machine code plus the exact `{{placeholder}}` values
 * that code's sentence needs (`MESSAGE_CODES` and `Finding.params` in
 * kuma_core/kuro/codon_import.py). It never sends a translated sentence, so a
 * message is translated once per locale instead of once per backend build.
 *
 * WHY A SWITCH AND NOT `t(\`codonTable.messages.${code}\`)`.
 * The template-literal form is the obvious implementation and it defeats the
 * gate that makes this arrangement safe. `scripts/i18n-parity.mjs` resolves
 * `t()` call sites statically: a template key lands in `dynamicKeyCalls` and an
 * options object built by spread or computed keys lands in
 * `opaqueOptionCalls`, and both buckets are reported without being checked.
 * Written that way, every message below would ship with zero placeholder
 * verification in ten locales. A literal key with a literal options object is
 * the only shape the check can read, so each code gets its own line.
 *
 * SCOPE OF THE CODES HANDLED HERE.
 * V1-V35 and N1, N2, N4 come from `MESSAGE_CODES`. N3 (leading and trailing
 * whitespace trimmed) is in that tuple but is never emitted - codon_import.py
 * calls it "silent by design" - so it has no string and falls to `unknown`.
 * The runtime rules R1 and R5 are deliberately absent: they are reported
 * through `failed[]`, which carries `{filename, code, reason}` and NO `params`
 * (kuma_core/kuro/codon_table.py, `CodonTableRegistry.scan`), so their
 * sentences cannot be rebuilt here. SettingsDialog renders those entries from
 * the code and the backend's English `reason` instead.
 */
import type { TFunction } from "i18next";

/**
 * Render one validator finding in the active locale.
 *
 * `params` is passed through verbatim from the backend. A code this build does
 * not know still produces a sentence naming the code, because a finding that
 * renders as an empty line is indistinguishable from no finding at all.
 */
export function formatCodonTableMessage(
  t: TFunction,
  code: string,
  params: Record<string, unknown>,
): string {
  switch (code) {
    case "V1":
      return t("codonTable.messages.V1", { ext: params.ext });
    case "V2":
      return t("codonTable.messages.V2", { size: params.size });
    case "V3":
      return t("codonTable.messages.V3", { line: params.line, col: params.col, detail: params.detail });
    case "V4":
      return t("codonTable.messages.V4", { type: params.type });
    case "V5":
      return t("codonTable.messages.V5", { n: params.n, max: params.max });
    case "V6":
      return t("codonTable.messages.V6", { reason: params.reason });
    case "V7":
      return t("codonTable.messages.V7", { key: params.key });
    case "V8":
      return t("codonTable.messages.V8", { stem: params.stem, key: params.key });
    case "V9":
      return t("codonTable.messages.V9", { key: params.key, name: params.name });
    case "V10":
      return t("codonTable.messages.V10", { key: params.key, name: params.name, date: params.date, sha8: params.sha8 });
    case "V11":
      return t("codonTable.messages.V11", { kept: params.kept });
    case "V12":
      return t("codonTable.messages.V12");
    case "V13":
      return t("codonTable.messages.V13", { value: params.value });
    case "V14":
      return t("codonTable.messages.V14", { n: params.n });
    case "V15":
      return t("codonTable.messages.V15", { n: params.n });
    case "V16":
      return t("codonTable.messages.V16", { codon: params.codon, declared: params.declared, n: params.n, expected: params.expected });
    case "V17":
      return t("codonTable.messages.V17", { missing: params.missing, extra: params.extra });
    case "V18":
      return t("codonTable.messages.V18", { missing: params.missing, dup: params.dup });
    case "V19":
      return t("codonTable.messages.V19", { codon: params.codon });
    case "V20":
      return t("codonTable.messages.V20", { codon: params.codon, n: params.n });
    case "V21":
      return t("codonTable.messages.V21", { codon: params.codon, value: params.value });
    case "V22":
      return t("codonTable.messages.V22", { aa: params.aa, sum: params.sum });
    case "V23":
      return t("codonTable.messages.V23", { aa: params.aa, sum: params.sum });
    case "V24":
      return t("codonTable.messages.V24", { aa: params.aa });
    case "V25":
      return t("codonTable.messages.V25", { codon: params.codon, value: params.value });
    case "V26":
      return t("codonTable.messages.V26", { diff: params.diff });
    case "V27":
      return t("codonTable.messages.V27", { codon: params.codon, stored: params.stored, computed: params.computed });
    case "V28":
      return t("codonTable.messages.V28", { alias: params.alias });
    case "V29":
      return t("codonTable.messages.V29", { alias: params.alias, other: params.other });
    case "V30":
      return t("codonTable.messages.V30", { alias: params.alias, other: params.other });
    case "V31":
      return t("codonTable.messages.V31", { cds: params.cds, codons: params.codons });
    case "V32":
      return t("codonTable.messages.V32");
    case "V33":
      return t("codonTable.messages.V33", { name: params.name });
    case "V34":
      return t("codonTable.messages.V34", { n: params.n, list: params.list });
    case "V35":
      return t("codonTable.messages.V35", { list: params.list });
    case "N1":
      return t("codonTable.messages.N1", { n: params.n });
    case "N2":
      return t("codonTable.messages.N2", { n: params.n });
    case "N4":
      return t("codonTable.messages.N4");
    default:
      return t("codonTable.messages.unknown", { code });
  }
}
