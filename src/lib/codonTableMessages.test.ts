/**
 * `formatCodonTableMessage`: every validator code the sidecar can emit reaches
 * a locale key, and every `{{placeholder}}` that key declares is fed from the
 * backend's `params`.
 *
 * The code list and the placeholder list are both read from their sources at
 * run time rather than transcribed here. A transcribed list turns this file
 * into a check of its own copy: adding V36 to `MESSAGE_CODES` would leave the
 * suite green while the new finding renders as "this version of kuma has no
 * description for it".
 *
 *   - codes:        `MESSAGE_CODES` in kuma_core/kuro/codon_import.py
 *   - placeholders: `codonTable.messages.*` in src/locales/en.json
 *
 * N3 is the one deliberate hole. It is in `MESSAGE_CODES` but codon_import.py
 * never emits it ("N3 is silent by design", the whitespace-trim normalization),
 * so it has no string and is expected to fall through to `unknown`. That is
 * asserted rather than excluded, so the day N3 starts being emitted this test
 * says so.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { TFunction } from "i18next";
import { formatCodonTableMessage } from "./codonTableMessages";

const REPO = resolve(__dirname, "../..");

/** Codes the backend declares, derived from the two comprehension ranges. */
function messageCodes(): string[] {
  const source = readFileSync(resolve(REPO, "kuma_core/kuro/codon_import.py"), "utf-8");
  const match = source.match(
    /MESSAGE_CODES[^=]*=\s*tuple\(\s*\[f"V\{i\}" for i in range\((\d+),\s*(\d+)\)\]\s*\+\s*\[f"N\{i\}" for i in range\((\d+),\s*(\d+)\)\]\s*,?\s*\)/,
  );
  if (!match) {
    throw new Error(
      "MESSAGE_CODES no longer matches the expected comprehension in "
      + "kuma_core/kuro/codon_import.py. Update this reader rather than "
      + "hardcoding the codes, or the suite checks nothing.",
    );
  }
  const [, vLo, vHi, nLo, nHi] = match.map(Number);
  const codes: string[] = [];
  for (let i = vLo; i < vHi; i += 1) codes.push(`V${i}`);
  for (let i = nLo; i < nHi; i += 1) codes.push(`N${i}`);
  return codes;
}

/**
 * Runtime rule codes, read from the scan that emits them.
 *
 * These are not in `MESSAGE_CODES`: they are produced by
 * `CodonTableRegistry.scan` rather than by a validator rule, and they reach the
 * frontend through `failed[].findings`. Derived here for the same reason the
 * V/N list is: a hardcoded ["R5"] would check its own copy.
 */
function runtimeCodes(): string[] {
  const source = readFileSync(resolve(REPO, "kuma_core/kuro/codon_table.py"), "utf-8");
  const found = [...source.matchAll(/"code":\s*"(R\d+)"/g)].map((m) => m[1]);
  if (found.length === 0) {
    throw new Error(
      "No runtime rule code found in kuma_core/kuro/codon_table.py. Update "
      + "this reader rather than hardcoding the codes.",
    );
  }
  return [...new Set(found)];
}

/** `codonTable.messages` as English ships it. */
function englishMessages(): Record<string, string> {
  const en = JSON.parse(readFileSync(resolve(REPO, "src/locales/en.json"), "utf-8"));
  return en.codonTable.messages as Record<string, string>;
}

/** Distinct placeholder names in a sentence; V9 uses `{{key}}` twice. */
function placeholdersOf(sentence: string): string[] {
  return [
    ...new Set([...sentence.matchAll(/\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g)].map((m) => m[1])),
  ];
}

interface Call { key: string; options: Record<string, unknown> }

/**
 * A `t` that records what it was asked for. Returning the key makes the
 * routing assertion readable; i18next's real interpolation is not under test.
 */
function recordingT(): { t: TFunction; calls: Call[] } {
  const calls: Call[] = [];
  const t = ((key: string, options: Record<string, unknown> = {}) => {
    calls.push({ key, options });
    return key;
  }) as unknown as TFunction;
  return { t, calls };
}

/**
 * `params` that reports which names the formatter read. Every property answers
 * `PARAM:<name>`, so the recorded options object shows both which placeholders
 * were filled and which backend field each one was filled from.
 */
function tracingParams(): Record<string, unknown> {
  return new Proxy({}, { get: (_t, prop) => `PARAM:${String(prop)}` });
}

const CODES = [...messageCodes(), ...runtimeCodes()];
const MESSAGES = englishMessages();
const SILENT_CODES = ["N3"];

describe("MESSAGE_CODES coverage", () => {
  it("CONTROL reads a non-empty code list containing both families", () => {
    expect(CODES.length).toBeGreaterThan(30);
    expect(CODES).toContain("V1");
    expect(CODES).toContain("N1");
    expect(CODES).toContain("N3");
    expect(CODES).toContain("R5");
  });

  it.each(CODES.filter((c) => !SILENT_CODES.includes(c)))(
    "routes %s to its own locale key",
    (code) => {
      const { t, calls } = recordingT();
      formatCodonTableMessage(t, code, tracingParams());
      expect(calls).toHaveLength(1);
      expect(calls[0].key).toBe(`codonTable.messages.${code}`);
    },
  );

  it.each(SILENT_CODES)(
    "leaves %s to the unknown fallback, because the backend never emits it",
    (code) => {
      const { t, calls } = recordingT();
      formatCodonTableMessage(t, code, {});
      expect(calls[0].key).toBe("codonTable.messages.unknown");
      expect(calls[0].options).toEqual({ code });
    },
  );

  it("has an English sentence for every code it routes", () => {
    const missing = CODES.filter(
      (c) => !SILENT_CODES.includes(c) && typeof MESSAGES[c] !== "string",
    );
    expect(missing).toEqual([]);
  });

  it("ships no sentence for a code nothing routes to", () => {
    const routed = new Set([...CODES.filter((c) => !SILENT_CODES.includes(c)), "unknown"]);
    expect(Object.keys(MESSAGES).filter((k) => !routed.has(k))).toEqual([]);
  });
});

describe("placeholder wiring", () => {
  it.each(CODES.filter((c) => !SILENT_CODES.includes(c)))(
    "fills every placeholder %s declares, from the identically named param",
    (code) => {
      const { t, calls } = recordingT();
      formatCodonTableMessage(t, code, tracingParams());
      const declared = placeholdersOf(MESSAGES[code]).sort();
      const supplied = Object.keys(calls[0].options).sort();
      // Both directions: a missing key leaves a raw {{x}} on screen, an extra
      // one means the call site reads a param the sentence never uses.
      expect(supplied).toEqual(declared);
      for (const name of declared) {
        // Catches a crossed wire such as t("...V5", { n: params.max }).
        expect(calls[0].options[name]).toBe(`PARAM:${name}`);
      }
    },
  );

  it("CONTROL: an unfilled placeholder is visible to the comparison above", () => {
    // The per-code assertion only means something if a placeholder left empty
    // actually shows up as one. V3 declares line, col and detail; hand it a
    // params object missing `detail` and the supplied value must be undefined
    // while the sentence still declares the name.
    const { t, calls } = recordingT();
    formatCodonTableMessage(t, "V3", { line: 1, col: 2 });
    expect(placeholdersOf(MESSAGES.V3)).toContain("detail");
    expect(calls[0].options.detail).toBeUndefined();
  });
});

describe("unknown codes", () => {
  it.each(["", "V0", "V36", "N5", "R1", "R6", "v1", "V1 ", "V1x", "1", "unknown", "ZZ"])(
    "falls back to the unknown sentence for %j",
    (code) => {
      const { t, calls } = recordingT();
      const rendered = formatCodonTableMessage(t, code, tracingParams());
      expect(rendered).toBe("codonTable.messages.unknown");
      expect(calls[0].options).toEqual({ code });
    },
  );

  it("names the code in the unknown sentence rather than rendering an empty line", () => {
    expect(placeholdersOf(MESSAGES.unknown)).toEqual(["code"]);
  });
});
